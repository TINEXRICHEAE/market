"""
Shopping App — views_balance_proof.py (REFINED)

Balance proof VERIFICATION & tier display.

Architecture:
  Payment App  → generates Groth16 proof via Strapi /api/generate-balance-proof
  Shopping App → verifies proof via Strapi /api/verify-balance-proof
  Seller sees  → tier (green/amber/red) + items_payable count. NEVER the balance.

Item inclusion rules:
  - payment_status = 'pending'  (not paid, deposited, or failed)
  - 'online' in payment_options (seller registered with Fair Cashier)
  - Scoped per seller-buyer pair (each seller only sees their own items)

item_details flow:
  Payment App computes per-item payability (shopping_order_item_id + payable bool).
  Shopping App stores and serves it so the template can border the RIGHT cards.
"""

import json
import logging
import requests as http_requests

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET

from .models import Order, OrderItem
from .zkp_client import ZKPClient

logger = logging.getLogger(__name__)

try:
    from .models import BalanceProofVerification
except ImportError:
    BalanceProofVerification = None
    logger.warning("BalanceProofVerification model not found — run migrations")


# ═══════════════════════════════════════════════════════════════════
# CONFIG HELPERS
# ═══════════════════════════════════════════════════════════════════

def _payment_url():
    return getattr(settings, 'PAYMENT_APP_URL', 'http://localhost:8001')


def _secret():
    return getattr(settings, 'SHOPPING_APP_INTERNAL_SECRET', '')


# ═══════════════════════════════════════════════════════════════════
# ITEM FILTERING — single source of truth for eligible items
# ═══════════════════════════════════════════════════════════════════

def _get_eligible_items_for_seller(order, seller_email):
    """
    Return OrderItem queryset filtered to items eligible for balance proof.

    Eligible means ALL of:
      - belongs to this seller
      - payment_status = 'pending'  (exclude paid/deposited/failed)
      - 'online' in payment_options (seller is registered with Fair Cashier)
    """
    return order.items.filter(
        seller__email=seller_email,
        payment_status__in=['failed', 'pending'],
        payment_options__contains='online',
    ).select_related('product', 'seller')


def _items_to_payload(items_qs):
    """Convert eligible OrderItem queryset to payload format for Payment App."""
    return [
        {
            'shopping_order_item_id': item.id,
            'amount': float(item.subtotal),
            'payment_method': item.payment_method,
        }
        for item in items_qs
    ]


# ═══════════════════════════════════════════════════════════════════
# STORAGE — read/write BalanceProofVerification records
# ═══════════════════════════════════════════════════════════════════

def _store_verification(order_number, seller_email, tier, payable, total,
                        bracket, verified, proof=None, pub=None,
                        expires_at=None, item_details=None, is_refresh=False):
    """Upsert a BalanceProofVerification record after verifying via Strapi."""
    if not BalanceProofVerification:
        return

    expires_dt = parse_datetime(expires_at) if isinstance(expires_at, str) else expires_at

    defaults = {
        'tier_result': tier,
        'items_payable': payable,
        'total_items': total,
        'binary_bracket': bracket,
        'verified': verified,
        'proof': proof,
        'public_signals': pub,
        'verified_at': timezone.now() if verified else None,
        'expires_at': expires_dt,
    }

    # Store item_details if the model field exists
    if item_details is not None:
        defaults['item_details'] = item_details

    try:
        obj, _ = BalanceProofVerification.objects.update_or_create(
            order_number=order_number,
            seller_email=seller_email,
            defaults=defaults,
        )
        if is_refresh:
            obj.refresh_count = (obj.refresh_count or 0) + 1
            obj.save(update_fields=['refresh_count'])
    except Exception as e:
        logger.error(f"Store verification failed: {e}")


def _get_stored_verification(order_number, seller_email):
    """Fetch a locally cached verification result."""
    if not BalanceProofVerification:
        return None
    try:
        v = BalanceProofVerification.objects.get(
            order_number=order_number, seller_email=seller_email)
        result = {
            'tier_result': v.tier_result,
            'items_payable': v.items_payable,
            'total_items': v.total_items,
            'verified': v.verified,
            'verified_at': v.verified_at.isoformat() if v.verified_at else None,
            'is_expired': v.is_expired,
            'refresh_count': v.refresh_count,
        }
        # Include item_details if the field exists on the model
        if hasattr(v, 'item_details'):
            result['item_details'] = v.item_details or []
        return result
    except BalanceProofVerification.DoesNotExist:
        return None


# ═══════════════════════════════════════════════════════════════════
# VERIFY — Shopping App verifies proof via Strapi
# ═══════════════════════════════════════════════════════════════════

def _verify_proof_via_strapi(proof, public_signals):
    """
    Call Strapi /api/verify-balance-proof to independently verify
    a Groth16 proof generated by the Payment App.
    """
    if not proof or not public_signals:
        return False
    try:
        result = ZKPClient().verify_balance_proof(proof, public_signals)
        return result.get('verified', False)
    except Exception as e:
        logger.error(f"Strapi balance proof verification error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PROOF REQUEST — called after order creation
# ═══════════════════════════════════════════════════════════════════

def request_balance_proofs_for_order(order):
    """
    Called from process_payment_selection() after Order + OrderItems are saved.

    1. Filters to eligible items per seller (pending + online-capable)
    2. POSTs to Payment App /internal/order-created/
    3. Payment App generates Groth16 proof per seller via Strapi
    4. We verify each proof independently via Strapi
    5. Store results (including per-item payability) in BalanceProofVerification
    """
    buyer_email = order.buyer.email

    # Get all eligible items, grouped by seller
    all_eligible = order.items.filter(
        payment_status='pending',
        payment_options__contains='online',
    ).select_related('seller')

    sellers_map = {}
    for item in all_eligible:
        se = item.seller.email
        if se not in sellers_map:
            sellers_map[se] = []
        sellers_map[se].append({
            'shopping_order_item_id': item.id,
            'amount': float(item.subtotal),
            'payment_method': item.payment_method,
        })

    if not sellers_map:
        logger.info(
            f"No eligible items for balance proof in order {order.order_number}")
        return None

    sellers_payload = [
        {'seller_email': email, 'items': items}
        for email, items in sellers_map.items()
    ]

    # Step 1: Ask Payment App to generate proofs
    try:
        resp = http_requests.post(
            f"{_payment_url()}/internal/order-created/",
            json={
                'order_id': order.order_number,
                'buyer_email': buyer_email,
                'sellers': sellers_payload,
            },
            headers={
                'X-Internal-Secret': _secret(),
                'Content-Type': 'application/json',
            },
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error(
                f"Payment App returned {resp.status_code}: {resp.text[:300]}")
            return None
        data = resp.json()
    except http_requests.exceptions.RequestException as e:
        logger.error(f"Balance proof request failed: {e}")
        return None

    # Step 2: Verify each proof independently via Strapi
    verified_proofs = []
    for pd in data.get('proofs', []):
        proof = pd.get('proof')
        pub = pd.get('public_signals')
        se = pd.get('seller_email', '')
        item_details = pd.get('item_details', [])

        ok = _verify_proof_via_strapi(proof, pub)

        verified_proofs.append({
            'seller_email': se,
            'tier_result': pd.get('tier_result', 'unknown'),
            'items_payable': pd.get('items_payable', 0),
            'total_items': pd.get('total_items', 0),
            'verified': ok,
            'item_details': item_details,
        })

        _store_verification(
            order.order_number, se,
            pd.get('tier_result', 'unknown'),
            pd.get('items_payable', 0),
            pd.get('total_items', 0),
            pd.get('binary_bracket', 0),
            ok, proof, pub,
            pd.get('expires_at'),
            item_details=item_details,
        )

    ok_count = sum(1 for p in verified_proofs if p['verified'])
    logger.info(
        f"Balance proofs for {order.order_number}: "
        f"{ok_count}/{len(verified_proofs)} verified via Strapi"
    )
    return {'order_id': order.order_number, 'proofs': verified_proofs}


# ═══════════════════════════════════════════════════════════════════
# REFRESH — seller-triggered re-generation + re-verification
# ═══════════════════════════════════════════════════════════════════

def refresh_balance_proof_for_seller(order, seller_email, include_cod=False):
    """
    Re-request a fresh proof from Payment App, then re-verify via Strapi.
    Re-filters to currently pending items only.
    """
    eligible = _get_eligible_items_for_seller(order, seller_email)
    items = _items_to_payload(eligible)

    if not items:
        logger.info(
            f"No pending eligible items for {seller_email} in "
            f"order {order.order_number}")
        _store_verification(
            order.order_number, seller_email,
            'green', 0, 0, 0, True,
            item_details=[],
            is_refresh=True,
        )
        return {
            'order_id': order.order_number,
            'seller_email': seller_email,
            'tier_result': 'green',
            'items_payable': 0,
            'total_items': 0,
            'verified': True,
            'refreshed_at': timezone.now().isoformat(),
            'include_cod': include_cod,
            'item_details': [],
            'note': 'All items paid — no pending items to prove',
        }

    # Step 1: Ask Payment App to regenerate proof
    try:
        resp = http_requests.post(
            f"{_payment_url()}/internal/balance-proof/refresh/",
            json={
                'order_id': order.order_number,
                'buyer_email': order.buyer.email,
                'seller_email': seller_email,
                'include_cod': include_cod,
                'items': items,
            },
            headers={
                'X-Internal-Secret': _secret(),
                'Content-Type': 'application/json',
            },
            timeout=60,
        )
        if resp.status_code != 200:
            logger.error(
                f"Refresh failed: Payment App returned {resp.status_code}")
            return None
        data = resp.json()
    except http_requests.exceptions.RequestException as e:
        logger.error(f"Refresh request failed: {e}")
        return None

    # Step 2: Verify the fresh proof via Strapi
    proof = data.get('proof')
    pub = data.get('public_signals')
    ok = _verify_proof_via_strapi(proof, pub)
    item_details = data.get('item_details', [])

    # Step 3: Store updated verification
    _store_verification(
        order.order_number, seller_email,
        data.get('tier_result', 'unknown'),
        data.get('items_payable', 0),
        data.get('total_items', 0),
        data.get('binary_bracket', 0),
        ok, proof, pub,
        data.get('expires_at'),
        item_details=item_details,
        is_refresh=True,
    )

    return {
        'order_id': order.order_number,
        'seller_email': seller_email,
        'tier_result': data.get('tier_result', 'unknown'),
        'items_payable': data.get('items_payable', 0),
        'total_items': data.get('total_items', 0),
        'verified': ok,
        'refreshed_at': data.get('refreshed_at') or data.get('generated_at'),
        'include_cod': include_cod,
        'item_details': item_details,
    }


# ═══════════════════════════════════════════════════════════════════
# API VIEWS — seller-facing endpoints
# ═══════════════════════════════════════════════════════════════════

@login_required
@require_GET
def api_buyer_balance_proof(request):
    """
    GET /api/buyer-balance-proof/?order_id=X

    Seller views the buyer's balance proof tier for THEIR items only.
    Only pending items with online payment options are included.
    Returns tier + items payable + item_details — never the actual balance.
    """
    order_id = request.GET.get('order_id', '')
    if not order_id:
        return JsonResponse({'error': 'order_id required'}, status=400)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

    seller_email = request.user.email

    # Check how many eligible items exist right now
    eligible_count = _get_eligible_items_for_seller(order, seller_email).count()

    if eligible_count == 0:
        total_seller_items = order.items.filter(seller__email=seller_email).count()
        paid_count = order.items.filter(
            seller__email=seller_email,
            payment_status='paid',
        ).count()

        if paid_count == total_seller_items and total_seller_items > 0:
            return JsonResponse({
                'tier': 'green',
                'items_payable': 0,
                'total_items': 0,
                'verified': True,
                'is_expired': False,
                'include_cod': False,
                'generated_at': None,
                'item_details': [],
                'note': 'All items already paid',
            })
        else:
            return JsonResponse({
                'tier': 'unknown',
                'items_payable': 0,
                'total_items': 0,
                'verified': False,
                'is_expired': False,
                'include_cod': False,
                'generated_at': None,
                'item_details': [],
                'note': 'No online-capable pending items for this seller',
            })

    # 1. Check locally cached verification (fast path)
    local = _get_stored_verification(order.order_number, seller_email)
    if local and not local.get('is_expired', False):
        return JsonResponse({
            'tier': local['tier_result'],
            'items_payable': local['items_payable'],
            'total_items': local['total_items'],
            'verified': local['verified'],
            'is_expired': False,
            'include_cod': False,
            'generated_at': local.get('verified_at'),
            'item_details': local.get('item_details', []),
        })

    # 2. Fallback: fetch from Payment App + verify via Strapi
    try:
        resp = http_requests.get(
            f"{_payment_url()}/internal/balance-proof/"
            f"?order_id={order.order_number}&seller_email={seller_email}",
            headers={'X-Internal-Secret': _secret()},
            timeout=15,
        )
        if resp.status_code == 200:
            d = resp.json()

            proof = d.get('proof')
            pub = d.get('public_signals')
            verified = _verify_proof_via_strapi(proof, pub)

            _store_verification(
                order.order_number, seller_email,
                d.get('tier_result', 'unknown'),
                d.get('items_payable', 0),
                d.get('total_items', 0),
                d.get('binary_bracket', 0),
                verified, proof, pub,
                d.get('expires_at'),
            )

            return JsonResponse({
                'tier': d.get('tier_result', 'unknown'),
                'items_payable': d.get('items_payable', 0),
                'total_items': d.get('total_items', 0),
                'verified': verified,
                'is_expired': d.get('is_expired', False),
                'include_cod': d.get('include_cod', False),
                'generated_at': d.get('generated_at'),
                'item_details': [],  # fetch endpoint doesn't store item_details
            })
    except Exception as e:
        logger.error(f"Balance proof fetch failed: {e}")

    return JsonResponse({
        'tier': 'unknown',
        'items_payable': 0,
        'total_items': eligible_count,
        'verified': False,
        'is_expired': False,
        'item_details': [],
    })


@login_required
@csrf_exempt
@require_http_methods(['POST'])
def api_buyer_balance_proof_refresh(request):
    """
    POST /api/buyer-balance-proof/refresh/ {order_id, include_cod?}

    Seller triggers a fresh proof cycle. Re-filters to currently
    pending items only — paid items since last check are excluded.
    """
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
        'item_details': result.get('item_details', []),
        'note': result.get('note', ''),
    })