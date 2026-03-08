"""
Shopping App - views_zkp.py (NEW)

Seller KYC ZKP registration + proof generation.
Uses: Users model + SellerVerification model (OneToOne via seller FK).

KYC field mapping:
  national_id      → SellerVerification.national_id_number
  date_of_birth    → SellerVerification.date_of_birth (DateField → YYYYMMDD)
  business_license → SellerVerification.business_registration_no
  tin              → SellerVerification.tin_number
  business_address → SellerVerification.business_address (fallback: physical_address)
"""

import json
import logging
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Users, SellerVerification
from .zkp_client import ZKPClient, encode_kyc_fields

logger = logging.getLogger(__name__)


# ─── GET status ───

@csrf_exempt
@require_http_methods(["GET", "POST"])
def seller_zkp_register(request):
    if request.method == 'GET':
        return _get_zkp_status(request)
    return _register_seller(request)


def _get_zkp_status(request):
    email = request.GET.get('email', '').strip().lower()
    if not email:
        return JsonResponse({'error': 'Email is required'}, status=400)

    try:
        sv = SellerVerification.objects.select_related('seller').get(seller__email=email)
    except SellerVerification.DoesNotExist:
        return JsonResponse({
            'email': email, 'kyc_approved': False,
            'zkp_status': 'not_registered', 'zkp_eligible': False,
        })

    tree_status = None
    try:
        tree_status = ZKPClient().get_kyc_tree_status()
    except Exception as e:
        logger.warning(f"Tree status fetch failed: {e}")

    return JsonResponse({
        'email': email,
        'kyc_approved': sv.is_approved,
        'zkp_status': sv.zkp_status,
        'zkp_eligible': sv.is_approved and sv.zkp_status == 'not_registered',
        'commitment_hash': sv.zkp_commitment_hash or '',
        'kyc_root': sv.zkp_merkle_root or '',
        'leaf_index': getattr(sv, 'zkp_leaf_index', None),
        'block_number': getattr(sv, 'zkp_block_number', None),
        'tree_status': tree_status,
        'registered_at': sv.zkp_registered_at.isoformat() if sv.zkp_registered_at else None,
    })


# ─── POST register ───

def _register_seller(request):
    is_admin = (
        request.user.is_authenticated
        and hasattr(request.user, 'role')
        and request.user.role in ('admin', 'superadmin')
    )
    is_internal = (
        request.headers.get('X-Internal-Secret', '')
        == getattr(settings, 'SHOPPING_APP_INTERNAL_SECRET', '')
    )
    if not is_admin and not is_internal:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    email = body.get('email', '').strip().lower()
    if not email:
        return JsonResponse({'error': 'Email is required'}, status=400)

    try:
        sv = SellerVerification.objects.select_related('seller').get(seller__email=email)
    except SellerVerification.DoesNotExist:
        return JsonResponse({'error': 'Seller KYC record not found'}, status=404)

    if not sv.is_approved:
        return JsonResponse({'error': f'KYC not approved. Status: {sv.status}'}, status=400)
    if sv.is_zkp_registered:
        return JsonResponse({
            'error': 'Already registered', 'zkp_status': 'registered',
            'commitment_hash': sv.zkp_commitment_hash,
        }, status=409)

    # Encode KYC fields
    encoded = encode_kyc_fields({
        'national_id': sv.national_id_number,
        'date_of_birth': sv.date_of_birth.strftime('%Y%m%d'),
        'business_license': sv.business_registration_no or '',
        'tin': sv.tin_number or '',
        'business_address': sv.business_address or sv.physical_address or '',
    })
    print(f"Encoded KYC for {email}: {encoded}")

    client = ZKPClient()

    # 1. Register in Merkle tree
    try:
        reg = client.register_seller(
            national_id=encoded['national_id'],
            date_of_birth=encoded['date_of_birth'],
            business_license=encoded['business_license'],
            tin=encoded['tin'],
            business_address=encoded['business_address'],
        )
    except Exception as e:
        logger.error(f"Strapi registration failed for {email}: {e}")
        sv.zkp_status = SellerVerification.ZKPStatus.FAILED
        sv.save(update_fields=['zkp_status', 'updated_at'])
        return JsonResponse({'error': 'ZKP registration failed', 'detail': str(e)}, status=502)

    commitment = reg.get('commitment', '')
    leaf_index = reg.get('leaf_index')
    kyc_root = reg.get('kyc_root', '')
    block_number = reg.get('block_number')
    tree_size = reg.get('tree_size')

    # 2. Generate PLONK proof
    proof = None
    public_signals = None
    proof_ok = False
    try:
        pr = client.generate_kyc_proof(
            national_id=encoded['national_id'],
            date_of_birth=encoded['date_of_birth'],
            business_license=encoded['business_license'],
            tin=encoded['tin'],
            business_address=encoded['business_address'],
            leaf_index=leaf_index,
        )
        print(f"Proof generation response for {email}: {pr}")
        proof = pr.get('proof')
        public_signals = pr.get('publicSignals')
        proof_ok = True
        print(f"Proof generated for {email}: proof={proof is not None}, public_signals={public_signals is not None}")
    except Exception as e:
        logger.warning(f"Proof generation failed for {email} (tree registration OK): {e}")

    # 3. Store on SellerVerification
    sv.record_zkp_registration(commitment_hash=commitment, merkle_root=kyc_root, proof=proof)
    sv.zkp_leaf_index = leaf_index
    sv.zkp_block_number = block_number
    sv.zkp_public_signals = public_signals
    sv.save(update_fields=['zkp_leaf_index', 'zkp_block_number', 'zkp_public_signals', 'updated_at'])

    logger.info(f"Seller ZKP registered: {email}, leaf={leaf_index}, proof={'yes' if proof_ok else 'no'}")

    return JsonResponse({
        'success': True, 'email': email, 'zkp_status': 'registered',
        'commitment_hash': commitment, 'leaf_index': leaf_index,
        'kyc_root': kyc_root, 'block_number': block_number,
        'tree_size': tree_size, 'proof_generated': proof_ok,
    })


# ─── Regenerate proof ───

@csrf_exempt
@require_http_methods(["POST"])
def seller_zkp_regenerate_proof(request):
    is_admin = request.user.is_authenticated and hasattr(request.user, 'role') and request.user.role in ('admin', 'superadmin')
    is_internal = request.headers.get('X-Internal-Secret', '') == getattr(settings, 'SHOPPING_APP_INTERNAL_SECRET', '')
    if not is_admin and not is_internal:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    body = json.loads(request.body)
    email = body.get('email', '').strip().lower()

    try:
        sv = SellerVerification.objects.select_related('seller').get(seller__email=email)
    except SellerVerification.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if not sv.is_zkp_registered:
        return JsonResponse({'error': 'Not registered yet'}, status=400)
    if sv.zkp_leaf_index is None:
        return JsonResponse({'error': 'Missing leaf_index'}, status=400)

    encoded = encode_kyc_fields({
        'national_id': sv.national_id_number,
        'date_of_birth': sv.date_of_birth.strftime('%Y%m%d'),
        'business_license': sv.business_registration_no or '',
        'tin': sv.tin_number or '',
        'business_address': sv.business_address or sv.physical_address or '',
    })
    print(f"Regenerating proof for {email} with encoded KYC: {encoded}")

    try:
        pr = ZKPClient().generate_kyc_proof(
            encoded['national_id'], encoded['date_of_birth'],
            encoded['business_license'], encoded['tin'],
            encoded['business_address'], sv.zkp_leaf_index,
        )
    except Exception as e:
        return JsonResponse({'error': 'Proof generation failed', 'detail': str(e)}, status=502)

    sv.zkp_proof_cached = pr.get('proof')
    sv.zkp_public_signals = pr.get('publicSignals')
    sv.save(update_fields=['zkp_proof_cached', 'zkp_public_signals', 'updated_at'])
    return JsonResponse({'success': True, 'email': email, 'proof_generated': True})


# ─── Internal API: Payment App fetches proof ───

@csrf_exempt
@require_http_methods(["GET"])
def internal_seller_zkp_proof(request, seller_email):
    """Payment App calls this. Returns proof+public_signals, NOT raw KYC."""
    secret = request.headers.get('X-Internal-Secret', '')
    if secret != getattr(settings, 'SHOPPING_APP_INTERNAL_SECRET', ''):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    email = seller_email.strip().lower()
    try:
        sv = SellerVerification.objects.select_related('seller').get(seller__email=email)
    except SellerVerification.DoesNotExist:
        return JsonResponse({'email': email, 'zkp_status': 'not_registered', 'error': 'Not found'}, status=404)

    if sv.is_zkp_registered and not sv.zkp_proof_cached:
        return JsonResponse({
            'email': email, 'zkp_status': 'registered',
            'error': 'Proof not yet generated', 'commitment_hash': sv.zkp_commitment_hash,
            'proof': None, 'public_signals': None,
        }, status=202)

    return JsonResponse({
        'email': email, 'zkp_status': sv.zkp_status,
        'commitment_hash': sv.zkp_commitment_hash or '',
        'leaf_index': getattr(sv, 'zkp_leaf_index', None),
        'kyc_root': sv.zkp_merkle_root or '',
        'block_number': getattr(sv, 'zkp_block_number', None),
        'registered_at': sv.zkp_registered_at.isoformat() if sv.zkp_registered_at else None,
        'proof': sv.zkp_proof_cached,
        'public_signals': getattr(sv, 'zkp_public_signals', None),
    })


# ─── Public status ───

@csrf_exempt
@require_http_methods(["GET"])
def seller_zkp_status(request, seller_email):
    email = seller_email.strip().lower()
    try:
        sv = SellerVerification.objects.get(seller__email=email)
    except SellerVerification.DoesNotExist:
        return JsonResponse({'email': email, 'zkp_registered': False, 'zkp_status': 'not_registered', 'kyc_approved': False})

    return JsonResponse({
        'email': email, 'zkp_status': sv.zkp_status,
        'zkp_registered': sv.is_zkp_registered, 'kyc_approved': sv.is_approved,
        'is_fully_verified': sv.is_fully_verified,
        'commitment_hash': sv.zkp_commitment_hash or '',
        'kyc_root': sv.zkp_merkle_root or '',
        'registered_at': sv.zkp_registered_at.isoformat() if sv.zkp_registered_at else None,
    })