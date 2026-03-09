# shopping_app/proxy_views.py
"""
E-commerce App - Fair Cashier Payment Gateway Proxy Layer
This module handles all communication with Fair Cashier payment system
"""

import requests
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction as db_transaction

from .models import Order, OrderItem

logger = logging.getLogger(__name__)

# Fair Cashier Configuration
FAIR_CASHIER_URL = getattr(settings, 'FAIR_CASHIER_API_URL', 'http://localhost:8001')
FAIR_CASHIER_API_KEY = getattr(settings, 'FAIR_CASHIER_API_KEY', '')


# ============= HELPER FUNCTIONS =============

def get_client_ip(request):
    """Extract client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def call_fair_cashier_api(endpoint, method='POST', data=None, timeout=15):
    """
    Centralized API caller for Fair Cashier
    
    Args:
        endpoint: API endpoint (e.g., '/api/check-sellers/')
        method: HTTP method
        data: Request payload
        timeout: Request timeout in seconds
    
    Returns:
        tuple: (success: bool, response_data: dict, status_code: int)
    """
    url = f"{FAIR_CASHIER_URL}{endpoint}"
    
    try:
        if method == 'POST':
            response = requests.post(
                url,
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=timeout
            )
        else:
            response = requests.get(url, params=data, timeout=timeout)
        
        response_data = response.json() if response.content else {}
        
        return (
            response.status_code in [200, 201],
            response_data,
            response.status_code
        )
        
    except requests.exceptions.Timeout:
        logger.error(f"Fair Cashier API timeout: {endpoint}")
        return False, {'error': 'Payment gateway timeout'}, 503
        
    except requests.exceptions.ConnectionError:
        logger.error(f"Fair Cashier connection error: {endpoint}")
        return False, {'error': 'Cannot connect to payment gateway'}, 503
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Fair Cashier request error: {str(e)}")
        return False, {'error': str(e)}, 500
        
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from Fair Cashier: {endpoint}")
        return False, {'error': 'Invalid response from payment gateway'}, 500


# ============= SELLER VERIFICATION =============

@login_required
@require_http_methods(["POST"])
def check_sellers_registration(request):
    """
    Check if sellers are registered with Fair Cashier
    
    Request: {"seller_emails": ["seller1@example.com", "seller2@example.com"]}
    Response: {
        "results": {
            "seller1@example.com": {"registered": true, "has_wallet": true, "has_pin": true},
            "seller2@example.com": {"registered": false, "has_wallet": false, "has_pin": false}
        }
    }
    """
    try:
        data = json.loads(request.body)
        seller_emails = data.get('seller_emails', [])
        
        success, response_data, status = call_fair_cashier_api(
            '/api/check-sellers/',
            data={
                'api_key': FAIR_CASHIER_API_KEY,
                'seller_emails': seller_emails
            }
        )
        
        if success:
            return JsonResponse(response_data)
        else:
            return JsonResponse(response_data, status=status)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error checking sellers: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# ============= PAYMENT IFRAME PROXY =============

@login_required
def payment_iframe_proxy(request, request_id):
    """
    Container page for Fair Cashier payment iframe
    
    This view embeds Fair Cashier's payment page in an iframe
    and handles postMessage communication
    """
    # Verify this is user's payment request
    pending_payment = request.session.get('pending_payment', {})
    
    if pending_payment.get('request_id') != str(request_id):
        logger.warning(
            f"⚠️ User {request.user.email} attempted unauthorized access to payment {request_id}"
        )
        return redirect('view_cart')
    
    context = {
        'payment_url': f'{FAIR_CASHIER_URL}/payment/{request_id}/',
        'request_id': request_id,
        'amount': pending_payment.get('amount', '0.00'),
        'order_number': pending_payment.get('order_number', 'N/A'),
        'fair_cashier_domain': FAIR_CASHIER_URL
    }
    
    return render(request, 'payment_iframe.html', context)


# ============= PAYMENT RETURN HANDLER =============

@login_required
def payment_return(request):
    """
    Handle return from Fair Cashier after payment.

    Query params:
    - request_id: Payment request UUID
    - status: success / failed / cancelled / deposited
    """
    request_id = request.GET.get('request_id')
    status = request.GET.get('status')

    logger.info(f"🔙 Payment return: {request_id} — Status: {status}")

    pending_payment = request.session.pop('pending_payment', {})
    order_id = pending_payment.get('order_id')
    order_number = pending_payment.get('order_number')
    online_item_ids = pending_payment.get('online_item_ids', [])

    if status == 'success':
        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.online_payment_status = 'completed'
                order.status = 'processing'
                order.save()

                if online_item_ids:
                    OrderItem.objects.filter(
                        id__in=online_item_ids,
                        order=order,
                        payment_status__in=['pending', 'failed'],
                    ).update(payment_status='paid', payment_method='online')

                logger.info(f"✅ Payment successful for order {order_number}")
                return redirect('view_order_detail', order_id=order_id)
            except Order.DoesNotExist:
                logger.error(f"Order {order_id} not found")
                return redirect('view_orders')
        return redirect('view_orders')

    elif status == 'deposited':
        # Buyer deposited funds to wallet but did not yet pay sellers
        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                # Leave online_payment_status as 'pending' — funds are in wallet, not settled
                order.save()

                # Mark items that were "deposited" — webhook will have already done this;
                # but as fallback, mark pending online items as deposited here too
                if online_item_ids:
                    OrderItem.objects.filter(
                        id__in=online_item_ids,
                        order=order,
                        payment_status__in=['pending', 'failed'],
                    ).update(payment_status='deposited')

                logger.info(f"💰 Deposit acknowledged for order {order_number}")
                from django.contrib import messages
                messages.success(request, 'Funds deposited to your wallet. Seller can see your payment is secured.')
                return redirect('view_order_detail', order_id=order_id)
            except Order.DoesNotExist:
                return redirect('view_orders')
        return redirect('view_orders')

    elif status == 'cancelled':
        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.online_payment_status = 'failed'
                order.status = 'cancelled'
                order.save()

                if online_item_ids:
                    OrderItem.objects.filter(
                        id__in=online_item_ids,
                        order=order,
                    ).update(payment_status='failed')
            except Order.DoesNotExist:
                pass

        logger.info(f"⚠️ Payment cancelled for order {order_number}")
        from django.contrib import messages
        messages.warning(request, 'Payment was cancelled.')
        return redirect('view_cart')

    else:
        # Failed
        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.online_payment_status = 'failed'
                order.status = 'cancelled'
                order.save()

                if online_item_ids:
                    OrderItem.objects.filter(
                        id__in=online_item_ids,
                        order=order,
                    ).update(payment_status='failed')
            except Order.DoesNotExist:
                pass

        logger.warning(f"⚠️ Payment failed for order {order_number}")
        from django.contrib import messages
        messages.error(request, 'Payment failed. Please try again.')
        return redirect('view_cart')


# ============= ADD NEW: payment_status_webhook =============

@csrf_exempt
@require_http_methods(["POST"])
def payment_status_webhook(request):
    """
    Webhook endpoint for Fair Cashier to push per-item payment status updates.

    Called by Fair Cashier payment app after processing items.

    Expected payload:
    {
        "request_id": "uuid",
        "item_updates": [
            {
                "shopping_order_item_id": 42,
                "status": "deposited" | "paid" | "failed",
                "amount": "5000.00"
            },
            ...
        ],
        "overall_status": "paid" | "deposited" | "partial" | "failed"
    }
    """
    try:
        data = json.loads(request.body)
        request_id = data.get('request_id')
        item_updates = data.get('item_updates', [])
        overall_status = data.get('overall_status', '')

        logger.info(f"📥 Payment status webhook: {request_id} — {overall_status}")

        if not request_id:
            return JsonResponse({'error': 'request_id required'}, status=400)

        # Find the order linked to this payment request
        try:
            order = Order.objects.get(fair_cashier_request_id=request_id)
        except Order.DoesNotExist:
            logger.error(f"❌ No order found for request {request_id}")
            return JsonResponse({'error': 'Order not found'}, status=404)

        with db_transaction.atomic():
            for update in item_updates:
                item_id = update.get('shopping_order_item_id')
                new_status = update.get('status')
                print(f"Updating item {item_id} to status {new_status}")
                
                if not item_id or not new_status:
                    continue

                try:
                    item = OrderItem.objects.get(id=item_id, order=order)
                    if new_status in ('paid', 'deposited') and item.payment_method != 'online':
                        item.payment_method = 'online'
                        item.save(update_fields=['payment_method'])
                except OrderItem.DoesNotExist:
                    logger.warning(f"Item {item_id} not found in order {order.id}")
                    continue

                if new_status not in ('paid', 'deposited', 'failed', 'pending'):
                    logger.warning(f"Unknown status '{new_status}' for item {item_id}")
                    continue

                updated = OrderItem.objects.filter(
                    id=item_id,
                    order=order,
                ).update(payment_status=new_status)

                logger.info(f"  Item {item_id} → {new_status} (updated: {updated})")

            # Update order-level status
            if overall_status == 'paid':
                order.online_payment_status = 'completed'
                order.status = 'processing'
            elif overall_status == 'deposited':
                # Funds in wallet, not yet settled
                order.online_payment_status = 'deposited'
            elif overall_status == 'partial':
                # Mix of paid + deposited — keep as processing
                order.online_payment_status = 'completed'
                order.status = 'processing'
            elif overall_status == 'failed':
                order.online_payment_status = 'failed'

            order.save()

        return JsonResponse({
            'status': 'ok',
            'order_number': order.order_number,
            'items_updated': len(item_updates),
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Internal error'}, status=500)



# ============= CHECK BUYER STATUS (FOR FAIR CASHIER) =============

@csrf_exempt
@require_http_methods(["GET", "POST"])
def check_buyer_fair_cashier_status(request):
    """
    Check if buyer exists in Fair Cashier system
    
    This is called by payment confirmation page to route buyer
    to either PIN setup or PIN login
    """
    if request.method == 'GET':
        email = request.GET.get('email')
    else:
        data = json.loads(request.body)
        email = data.get('email')
    
    if not email:
        return JsonResponse({'error': 'Email required'}, status=400)
    
    # Call Fair Cashier API
    success, response_data, status = call_fair_cashier_api(
        '/api/check-buyer-status/',
        method='GET',
        data={'email': email}
    )
    
    if success:
        return JsonResponse(response_data)
    else:
        # Default to setup if API fails
        return JsonResponse({
            'exists': False,
            'has_pin': False,
            'has_wallet': False,
            'action': 'pin_setup',
            'is_locked': False
        })


# ============= HELPER: GET SELLER PAYMENT OPTIONS =============

def get_seller_payment_options(seller_email):
    """
    Quick check if seller accepts online payment
    
    Returns: {'online': bool, 'cash': bool}
    """
    success, response_data, _ = call_fair_cashier_api(
        '/api/check-sellers/',
        data={
            'api_key': FAIR_CASHIER_API_KEY,
            'seller_emails': [seller_email]
        },
        timeout=5
    )
    
    if success:
        results = response_data.get('results', {})
        seller_data = results.get(seller_email, {})
        
        return {
            'online': seller_data.get('registered', False) and seller_data.get('has_wallet', False),
            'cash': True  # Cash always available
        }
    
    # Default to cash only on error
    return {'online': False, 'cash': True}