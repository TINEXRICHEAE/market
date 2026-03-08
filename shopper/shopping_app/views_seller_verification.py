# shopping_app/views_seller_verification.py
"""
Seller KYC submission, status, and verification API endpoints.
ZKP registration is handled by views_zkp.py (auto-triggered from admin.py on approval).
"""

import json
import logging
import requests as http_requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.utils import timezone

from .models import Users, SellerVerification
from .forms import SellerVerificationForm

logger = logging.getLogger(__name__)


def _require_seller(user):
    return user.is_authenticated and user.role == 'seller'


def _internal_secret():
    return getattr(settings, 'SHOPPING_APP_INTERNAL_SECRET', '')


def _payment_app_url():
    return getattr(settings, 'PAYMENT_APP_URL', 'http://localhost:8001')



# ─────────────────────────────────────────────────────────────────────────────
# 1. KYC submission form
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def seller_kyc_submit(request):
    if not _require_seller(request.user):
        return render(request, 'seller_kyc_access_denied.html', status=403)

    try:
        kyc = SellerVerification.objects.get(seller=request.user)
    except SellerVerification.DoesNotExist:
        kyc = None

    if kyc and kyc.status == SellerVerification.VerificationStatus.APPROVED:
        return redirect('seller_kyc_status')

    if request.method == 'POST':
        form = SellerVerificationForm(request.POST, request.FILES, instance=kyc)
        if form.is_valid():
            kyc_obj = form.save(commit=False)
            kyc_obj.seller = request.user
            kyc_obj.status = SellerVerification.VerificationStatus.PENDING
            kyc_obj.save()
            logger.info(f"Seller KYC submitted: {request.user.email}")
            return redirect('seller_kyc_status')
    else:
        form = SellerVerificationForm(instance=kyc)

    return render(request, 'seller_verification_form.html', {
        'form': form, 'kyc': kyc, 'created': kyc is None,
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. Seller's own KYC status page
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def seller_kyc_status(request):
    if not _require_seller(request.user):
        return render(request, 'seller_kyc_access_denied.html', status=403)

    try:
        kyc = SellerVerification.objects.get(seller=request.user)
    except SellerVerification.DoesNotExist:
        return redirect('seller_kyc_submit')

    return render(request, 'seller_verification_status.html', {'kyc': kyc})


# ─────────────────────────────────────────────────────────────────────────────
# 3. AJAX — buyer/seller checks a seller's verification status
#    GET /api/seller-verification-status/<seller_id>/
#    Used by payment_selection.html and order_detail.html badges.
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# 3. AJAX — buyer/seller checks a seller's verification status
#    GET /api/seller-verification-status/<seller_id>/
# ─────────────────────────────────────────────────────────────────────────────



@login_required
@require_GET
def api_seller_verification_status(request, seller_id):
    """
    Returns KYC + ZKP verification status for a seller.
    ?refresh=1 fetches live status from Payment App.
    """
    refresh = request.GET.get('refresh') == '1'

    try:
        seller = Users.objects.get(id=seller_id, role='seller')
    except Users.DoesNotExist:
        return JsonResponse({'error': 'Seller not found'}, status=404)

    try:
        kyc = SellerVerification.objects.get(seller=seller)
    except SellerVerification.DoesNotExist:
        return JsonResponse({
            'seller_id': seller.id, 'seller_email': seller.email,
            'kyc_approved': False, 'kyc_status': 'incomplete',
            'zkp_status': 'not_registered', 'zkp_valid': False,
            'merkle_root': None, 'block_number': None, 'tree_size': None,
            'verified_at': None, 'commitment_hash': None,
            'business_name': '',
        })

    kyc_approved = kyc.is_approved
    response = {
        'seller_id': seller.id,
        'seller_email': seller.email,
        'kyc_approved': kyc_approved,
        'kyc_status': kyc.status,
        'zkp_status': kyc.zkp_status,
        'commitment_hash': kyc.zkp_commitment_hash or None,
        'business_name': kyc.business_name or '',
    }

    if not kyc_approved or kyc.zkp_status != 'registered':
        return JsonResponse(response)

    # Fetch actual verification status from Payment App
    if refresh or not kyc.zkp_last_verified_at:
        result = _refresh_zkp_verification(kyc)
        response['zkp_valid'] = result.get('valid', False)
        response['verified_at'] = result.get('verified_at')
        response['commitment_match'] = result.get('commitment_match', False)
        # Keep block_number/tree_size from local registration data
        response['block_number'] = getattr(kyc, 'zkp_block_number', None)
    else:
        # Cached — use last known status
        response['zkp_valid'] = True
        response['block_number'] = getattr(kyc, 'zkp_block_number', None)

    return JsonResponse(response)


def _refresh_zkp_verification(kyc):
    """
    Fetch the seller's ACTUAL verification status from the Payment App.

    The Payment App is the one that verified the proof via Strapi /verify-kyc-proof.
    Its User model has the ground-truth fields:
      - zkp_verified (bool)
      - zkp_verified_at (datetime)
      - zkp_kyc_root (Merkle root at verification time)
      - zkp_commitment_hash (from the proof it verified)

    We call: GET Payment App /api/internal/seller-zkp-status/<email>/
    Then cross-check commitment_hash to confirm both apps agree on identity.

    Returns:
        dict with {valid, verified_at, kyc_root, commitment_match}
    """
    seller_email = kyc.seller.email
    result = {'valid': False, 'verified_at': None, 'kyc_root': None, 'commitment_match': False}

    try:
        resp = http_requests.get(
            f"{_payment_app_url()}/api/internal/seller-zkp-status/{seller_email}/",
            headers={'X-Internal-Secret': _internal_secret()},
            timeout=15,
        )

        if resp.status_code == 404:
            # Seller doesn't exist in Payment App yet — not verified
            logger.info(f"Seller {seller_email} not found in Payment App")
            return result

        if resp.status_code != 200:
            logger.warning(
                f"Payment App returned {resp.status_code} for "
                f"seller ZKP status: {seller_email}"
            )
            return result

        data = resp.json()

    except http_requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch seller ZKP status from Payment App: {e}")
        return result

    # Extract Payment App's ground-truth verification fields
    pa_verified = data.get('zkp_verified', False)
    pa_verified_at = data.get('zkp_verified_at')
    pa_kyc_root = data.get('zkp_kyc_root', '')
    pa_commitment = data.get('zkp_commitment_hash', '')

    # Cross-check: does Payment App's commitment_hash match ours?
    local_commitment = kyc.zkp_commitment_hash or ''
    commitment_match = (
        bool(pa_commitment) and
        bool(local_commitment) and
        pa_commitment == local_commitment
    )

    if not commitment_match and pa_commitment and local_commitment:
        logger.warning(
            f"Commitment hash MISMATCH for {seller_email}: "
            f"Shopping App={local_commitment[:20]}... "
            f"Payment App={pa_commitment[:20]}..."
        )

    # Seller is valid only if:
    #   1. Payment App has verified the proof (zkp_verified=True)
    #   2. Commitment hashes match between both apps
    is_valid = pa_verified and commitment_match

    result['valid'] = is_valid
    result['verified_at'] = pa_verified_at
    result['kyc_root'] = pa_kyc_root
    result['commitment_match'] = commitment_match

    # Update local cache with Payment App's verified timestamp
    try:
        update_fields = ['updated_at']

        if pa_verified_at:
            from django.utils.dateparse import parse_datetime
            parsed = parse_datetime(pa_verified_at)
            if parsed:
                kyc.zkp_last_verified_at = parsed
                update_fields.append('zkp_last_verified_at')

        if pa_kyc_root:
            kyc.zkp_merkle_root = pa_kyc_root
            update_fields.append('zkp_merkle_root')

        kyc.save(update_fields=update_fields)
    except Exception as e:
        logger.warning(f"Failed to cache verification status for {seller_email}: {e}")

    logger.info(
        f"ZKP verification refresh for {seller_email}: "
        f"valid={is_valid}, pa_verified={pa_verified}, "
        f"commitment_match={commitment_match}"
    )

    return result



# ─────────────────────────────────────────────────────────────────────────────
# 4. Navbar badge — seller's own KYC status (lightweight)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_GET
def api_seller_kyc_status(request):
    """GET /api/seller/kyc-status/ — navbar badge, no ZKP check."""
    if request.user.role != 'seller':
        return JsonResponse({'status': 'not_seller'}, status=403)

    try:
        kyc = SellerVerification.objects.get(seller=request.user)
        return JsonResponse({
            'status': kyc.status,
            'zkp_status': kyc.zkp_status,
        })
    except SellerVerification.DoesNotExist:
        return JsonResponse({'status': 'incomplete', 'zkp_status': 'not_registered'})


# ─────────────────────────────────────────────────────────────────────────────
# 5. INTERNAL endpoint — payment app fetches seller KYC data
#    GET/PATCH /internal/seller-kyc/<seller_email>/
# ─────────────────────────────────────────────────────────────────────────────

def _check_internal_secret(request):
    secret = getattr(settings, 'SHOPPING_APP_INTERNAL_SECRET', '')
    provided = request.headers.get('X-Internal-Secret', '')
    if not secret or provided != secret:
        return False
    return True


@csrf_exempt
@require_http_methods(['GET', 'PATCH'])
def internal_seller_kyc_data(request, seller_email):
    """
    GET  → KYC fields for ZKP (used by payment app if needed).
    PATCH → Update ZKP status from payment app (legacy — now Shopping App does registration).
    """
    if not _check_internal_secret(request):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        seller = Users.objects.get(email=seller_email, role='seller')
    except Users.DoesNotExist:
        return JsonResponse({'error': 'Seller not found'}, status=404)

    if request.method == 'GET':
        try:
            kyc = SellerVerification.objects.get(seller=seller)
        except SellerVerification.DoesNotExist:
            return JsonResponse({
                'seller_email': seller_email,
                'kyc_approved': False, 'kyc_status': 'incomplete',
                'zkp_status': 'not_registered',
            })

        dob = kyc.date_of_birth
        return JsonResponse({
            'seller_email': seller_email,
            'kyc_approved': kyc.is_approved,
            'kyc_status': kyc.status,
            'zkp_status': kyc.zkp_status,
            'zkp_commitment_hash': kyc.zkp_commitment_hash,
            'zkp_merkle_root': kyc.zkp_merkle_root,
            'national_id_number': kyc.national_id_number,
            'date_of_birth': dob.strftime('%Y-%m-%d') if dob else None,
            'business_registration_no': kyc.business_registration_no or '',
            'tin_number': kyc.tin_number or '',
            'business_address': kyc.business_address or kyc.physical_address or '',
            'district': kyc.district or '',
        })

    # PATCH — legacy support for payment app updating ZKP status
    if request.method == 'PATCH':
        try:
            body = json.loads(request.body)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        try:
            kyc = SellerVerification.objects.get(seller=seller)
        except SellerVerification.DoesNotExist:
            return JsonResponse({'error': 'KYC record not found'}, status=404)

        update_fields = []
        for field, model_field in [
            ('zkp_status', 'zkp_status'),
            ('zkp_commitment_hash', 'zkp_commitment_hash'),
            ('zkp_merkle_root', 'zkp_merkle_root'),
        ]:
            val = body.get(field)
            if val is not None:
                setattr(kyc, model_field, val)
                update_fields.append(model_field)

        leaf_index = body.get('leaf_index')
        if leaf_index is not None:
            kyc.zkp_leaf_index = leaf_index
            update_fields.append('zkp_leaf_index')

        block_number = body.get('block_number')
        if block_number is not None:
            kyc.zkp_block_number = block_number
            update_fields.append('zkp_block_number')

        if update_fields:
            kyc.zkp_last_verified_at = timezone.now()
            update_fields.append('zkp_last_verified_at')
            kyc.save(update_fields=update_fields)

        return JsonResponse({'success': True, 'updated_fields': update_fields})


# ─────────────────────────────────────────────────────────────────────────────
# 6. Buyer balance proof endpoints (seller-facing)
#    GET  /api/buyer-balance-proof/?order_id=X
#    POST /api/buyer-balance-proof/refresh/
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_GET
def api_buyer_balance_proof(request):
    """
    Seller views the buyer's balance proof tier for their order.
    GET /api/buyer-balance-proof/?order_id=X
    Returns tier (green/amber/red) — never the actual balance.
    """
    from .models import Order
    from .views_balance_proof import _get_stored

    order_id = request.GET.get('order_id', '')
    if not order_id:
        return JsonResponse({'error': 'order_id required'}, status=400)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

    seller_email = request.user.email

    # Check local verification first
    local = _get_stored(order.order_number, seller_email)
    if local:
        return JsonResponse({
            'tier': local['tier_result'],
            'items_payable': local['items_payable'],
            'total_items': local['total_items'],
            'verified': local['verified'],
            'is_expired': local.get('is_expired', False),
            'include_cod': False,
            'generated_at': local.get('verified_at'),
        })

    # Fallback: fetch from Payment App
    import requests as http_req
    payment_url = getattr(settings, 'PAYMENT_APP_URL', 'http://localhost:8001')
    secret = getattr(settings, 'SHOPPING_APP_INTERNAL_SECRET', '')

    try:
        resp = http_req.get(
            f"{payment_url}/internal/balance-proof/"
            f"?order_id={order.order_number}&seller_email={seller_email}",
            headers={'X-Internal-Secret': secret}, timeout=15,
        )
        if resp.status_code == 200:
            d = resp.json()
            return JsonResponse({
                'tier': d.get('tier_result', 'unknown'),
                'items_payable': d.get('items_payable', 0),
                'total_items': d.get('total_items', 0),
                'verified': False,
                'is_expired': d.get('is_expired', False),
                'include_cod': d.get('include_cod', False),
                'generated_at': d.get('generated_at'),
            })
    except Exception as e:
        logger.error(f"Balance proof fetch failed: {e}")

    return JsonResponse({
        'tier': 'unknown', 'items_payable': 0, 'total_items': 0,
        'verified': False, 'is_expired': False,
    })


@login_required
@csrf_exempt
@require_http_methods(['POST'])
def api_buyer_balance_proof_refresh(request):
    """POST /api/buyer-balance-proof/refresh/ {order_id}"""
    from .models import Order
    from .views_balance_proof import refresh_balance_proof_for_seller

    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    order_id = body.get('order_id', '')
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

    seller_email = request.user.email
    include_cod = body.get('include_cod', False)

    result = refresh_balance_proof_for_seller(order, seller_email, include_cod)
    if not result:
        return JsonResponse({'error': 'Refresh failed'}, status=502)

    return JsonResponse({
        'tier': result.get('tier_result', 'unknown'),
        'items_payable': result.get('items_payable', 0),
        'total_items': result.get('total_items', 0),
        'verified': result.get('verified', False),
        'refreshed_at': result.get('refreshed_at'),
        'include_cod': include_cod,
    })