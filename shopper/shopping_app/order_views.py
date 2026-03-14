# File: shopping_app/order_views.py

import logging
import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction as db_transaction
from django.db.models import Q, Count, Prefetch
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
import requests as http_requests

from .models import (
    Users, Order, OrderItem, OrderItemTracking,
    DeliveryConfirmation, OrderDispute,
)

logger = logging.getLogger(__name__)

FAIR_CASHIER_URL = getattr(settings, 'FAIR_CASHIER_API_URL', 'http://localhost:8001')
FAIR_CASHIER_API_KEY = getattr(settings, 'FAIR_CASHIER_API_KEY', '')


# ═══════════════════════════════════════════════════════════════════════════
#  SELLER — ORDER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='login_user')
def seller_orders_page(request):
    """Render the seller orders management page."""
    if request.user.role != 'seller':
        return redirect('home')
    return render(request, 'seller_orders.html')


@login_required(login_url='login_user')
@api_view(['GET'])
def get_seller_orders(request):
    """
    Get all orders containing items sold by this seller.
    Groups order items by order, with buyer info and payment details.
    """
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        # Get order items for this seller, grouped by order
        order_items = OrderItem.objects.filter(
            seller=request.user
        ).select_related(
            'order', 'order__buyer', 'product'
        ).order_by('-order__created_at')

        # Group by order
        orders_map = {}
        for item in order_items:
            oid = item.order.id
            if oid not in orders_map:
                buyer = item.order.buyer
                orders_map[oid] = {
                    'order_id': oid,
                    'order_number': item.order.order_number,
                    'buyer_email': buyer.email,
                    'buyer_phone': str(buyer.phonenumber) if buyer.phonenumber else None,
                    'order_status': item.order.status,
                    'order_status_display': item.order.get_status_display(),
                    'created_at': item.order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'items': [],
                    'total_amount': Decimal('0.00'),
                }
            orders_map[oid]['items'].append({
                'item_id': item.id,
                'product_name': item.product.name,
                'product_image': item.product.image_display_url or item.product.image_url,
                'quantity': item.quantity,
                'price': str(item.price),
                'subtotal': str(item.subtotal),
                'payment_method': item.payment_method,
                'payment_method_display': item.get_payment_method_display(),
                'payment_status': item.payment_status,
                'payment_status_display': item.get_payment_status_display(),
                'tracking_status': item.tracking_status,
                'tracking_status_display': item.get_tracking_status_display(),
                'tracking_number': item.tracking_number,
                'has_dispute': item.has_dispute,
            })
            orders_map[oid]['total_amount'] += item.subtotal

        # Convert to list, serialise Decimal
        orders_list = []
        for o in orders_map.values():
            o['total_amount'] = str(o['total_amount'])
            orders_list.append(o)

        return Response({'orders': orders_list})

    except Exception as e:
        logger.error(f"Error fetching seller orders: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
def seller_order_detail_page(request, order_id):
    """Render seller's order detail / tracking page."""
    if request.user.role != 'seller':
        return redirect('home')
    return render(request, 'seller_order_detail.html', {'order_id': order_id})


@login_required(login_url='login_user')
@api_view(['GET'])
def get_seller_order_detail(request, order_id):
    """
    Full detail of an order from the seller's perspective.
    Includes buyer contact info, item tracking, payment info, dispute info.
    """
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        order = get_object_or_404(Order, id=order_id)

        # Ensure this seller has items in this order
        seller_items = order.items.filter(seller=request.user).select_related('product')
        if not seller_items.exists():
            return Response({'error': 'No items found for this seller in this order'}, status=404)

        buyer = order.buyer
        items_data = []
        for item in seller_items:
            # Get tracking history
            history = OrderItemTracking.objects.filter(order_item=item).order_by('created_at')
            tracking_history = [{
                'status': h.status,
                'notes': h.notes,
                'updated_by': h.updated_by_role,
                'created_at': h.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            } for h in history]

            # Get dispute info if any
            dispute_info = None
            if item.has_dispute:
                try:
                    d = item.dispute
                    dispute_info = {
                        'dispute_id': d.dispute_id,
                        'complaint_type': d.get_complaint_type_display(),
                        'description': d.description,
                        'status': d.status,
                        'status_display': d.get_status_display(),
                        'payment_app_status': d.payment_app_status,
                        'refund_amount': str(d.refund_amount) if d.refund_amount else None,
                        'admin_notes': d.admin_notes,
                        'created_at': d.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'resolved_at': d.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if d.resolved_at else None,
                    }
                except OrderDispute.DoesNotExist:
                    pass

            items_data.append({
                'item_id': item.id,
                'product_name': item.product.name,
                'product_image': item.product.image_display_url or item.product.image_url,
                'quantity': item.quantity,
                'price': str(item.price),
                'subtotal': str(item.subtotal),
                'payment_method': item.payment_method,
                'payment_method_display': item.get_payment_method_display(),
                'payment_status': item.payment_status,
                'payment_status_display': item.get_payment_status_display(),
                'tracking_status': item.tracking_status,
                'tracking_status_display': item.get_tracking_status_display(),
                'tracking_number': item.tracking_number,
                'dispatch_date': item.dispatch_date.strftime('%Y-%m-%d %H:%M') if item.dispatch_date else None,
                'estimated_delivery': item.estimated_delivery.strftime('%Y-%m-%d %H:%M') if item.estimated_delivery else None,
                'delivery_notes': item.delivery_notes,
                'has_dispute': item.has_dispute,
                'dispute': dispute_info,
                'tracking_history': tracking_history,
            })

        return Response({
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'status': order.status,
                'status_display': order.get_status_display(),
                'buyer_email': buyer.email,
                'buyer_phone': str(buyer.phonenumber) if buyer.phonenumber else None,
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            },
            'items': items_data,
        })

    except Exception as e:
        logger.error(f"Error fetching seller order detail: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def update_order_item_tracking(request, item_id):
    """
    Seller updates the tracking status of a specific order item.

    POST body: {
        "status": "dispatched",
        "tracking_number": "TRK-123456",     // optional
        "notes": "Shipped via DHL",           // optional
        "estimated_delivery": "2026-02-20"    // optional
    }
    """
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        order_item = get_object_or_404(OrderItem, id=item_id, seller=request.user)

        new_status = request.data.get('status')
        valid_statuses = [c[0] for c in OrderItem.TRACKING_STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Must be one of: {valid_statuses}'}, status=400)

        notes = request.data.get('notes', '')
        tracking_number = request.data.get('tracking_number')
        estimated_delivery = request.data.get('estimated_delivery')

        with db_transaction.atomic():
            old_status = order_item.tracking_status
            order_item.tracking_status = new_status

            if tracking_number:
                order_item.tracking_number = tracking_number
            if estimated_delivery:
                from datetime import datetime
                order_item.estimated_delivery = datetime.fromisoformat(estimated_delivery)
            if new_status == 'dispatched':
                order_item.dispatch_date = timezone.now()
            if new_status == 'delivered_by_seller':
                order_item.delivery_marked_at = timezone.now()
                if order_item.payment_status not in ('paid', 'escrowed'):
                    if order_item.payment_method == 'online':
                        # Online payment not completed — fall back to cash on delivery
                        order_item.payment_method = 'cash'
                        order_item.delivery_notes = (order_item.delivery_notes or '') + \
                            '\nOnline payment not completed — switched to cash on delivery.'
                    order_item.payment_status = 'paid'
            if notes:
                order_item.delivery_notes = notes

            order_item.save()

            # Create tracking history record
            OrderItemTracking.objects.create(
                order_item=order_item,
                status=new_status,
                notes=notes or f"Status changed from {old_status} to {new_status}",
                updated_by_role='seller',
                updated_by=request.user,
            )

            # If status is delivered_by_seller, check if ALL seller items in this order
            # are marked delivered — if so, trigger the buyer confirmation
            if new_status == 'delivered_by_seller':
                _check_and_create_delivery_confirmation(order_item.order, request.user)

            # Update overall order status
            _update_order_status(order_item.order)

        return Response({
            'success': True,
            'message': f'Item tracking updated to {new_status}',
            'tracking_status': new_status,
        })

    except Exception as e:
        logger.error(f"Error updating tracking: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def bulk_update_tracking(request, order_id):
    """
    Seller updates tracking status for multiple items at once.

    POST body: {
        "item_ids": [1, 2, 3],
        "status": "dispatched",
        "tracking_number": "TRK-123456",
        "notes": "All items shipped together"
    }
    """
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        item_ids = request.data.get('item_ids', [])
        new_status = request.data.get('status')
        notes = request.data.get('notes', '')
        tracking_number = request.data.get('tracking_number')

        if not item_ids:
            return Response({'error': 'No items selected'}, status=400)

        with db_transaction.atomic():
            items = OrderItem.objects.filter(
                id__in=item_ids,
                seller=request.user,
                order_id=order_id
            )

            for item in items:
                old_status = item.tracking_status
                item.tracking_status = new_status
                if tracking_number:
                    item.tracking_number = tracking_number
                if new_status == 'dispatched':
                    item.dispatch_date = timezone.now()
                if new_status == 'delivered_by_seller':
                    item.delivery_marked_at = timezone.now()
                    if item.payment_status not in ('paid', 'escrowed'):
                        if item.payment_method == 'online':
                            # Online payment not completed — fall back to cash on delivery
                            item.payment_method = 'cash'
                            item.delivery_notes = (item.delivery_notes or '') + \
                                '\nOnline payment not completed — switched to cash on delivery.'
                        item.payment_status = 'paid'
                item.save()

                OrderItemTracking.objects.create(
                    order_item=item,
                    status=new_status,
                    notes=notes or f"Bulk update: {old_status} → {new_status}",
                    updated_by_role='seller',
                    updated_by=request.user,
                )

            # Check delivery confirmation
            order = get_object_or_404(Order, id=order_id)
            if new_status == 'delivered_by_seller':
                _check_and_create_delivery_confirmation(order, request.user)
            _update_order_status(order)

        return Response({
            'success': True,
            'message': f'{items.count()} items updated to {new_status}',
        })

    except Exception as e:
        logger.error(f"Error in bulk tracking update: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════
#  BUYER — ORDER TRACKING
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='login_user')
def buyer_order_tracking_page(request, order_id):
    """Render the buyer's order tracking page."""
    return render(request, 'buyer_order_tracking.html', {'order_id': order_id})


@login_required(login_url='login_user')
@api_view(['GET'])
def get_buyer_order_tracking(request, order_id):
    """
    Full order tracking data for the buyer, grouped by seller.
    Includes per-item tracking status, history, and dispute info.
    """
    try:
        order = get_object_or_404(Order, id=order_id, buyer=request.user)

        items = order.items.select_related('product', 'seller').all()

        # Group by seller
        sellers_map = {}
        for item in items:
            s_email = item.seller.email
            if s_email not in sellers_map:
                sellers_map[s_email] = {
                    'seller_email': s_email,
                    'seller_phone': str(item.seller.phonenumber) if item.seller.phonenumber else None,
                    'items': [],
                }

            # Get tracking history
            history = OrderItemTracking.objects.filter(order_item=item).order_by('created_at')
            tracking_history = [{
                'status': h.status,
                'notes': h.notes,
                'updated_by': h.updated_by_role,
                'created_at': h.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            } for h in history]

            # Dispute info
            dispute_info = None
            if item.has_dispute:
                try:
                    d = item.dispute
                    dispute_info = {
                        'dispute_id': d.dispute_id,
                        'complaint_type': d.get_complaint_type_display(),
                        'description': d.description,
                        'status': d.status,
                        'status_display': d.get_status_display(),
                        'payment_app_status': d.payment_app_status,
                        'refund_amount': str(d.refund_amount) if d.refund_amount else None,
                        'admin_notes': d.admin_notes,
                        'created_at': d.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'resolved_at': d.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if d.resolved_at else None,
                    }
                except OrderDispute.DoesNotExist:
                    pass

            sellers_map[s_email]['items'].append({
                'item_id': item.id,
                'product_name': item.product.name,
                'product_image': item.product.image_display_url or item.product.image_url,
                'quantity': item.quantity,
                'price': str(item.price),
                'subtotal': str(item.subtotal),
                'payment_method': item.payment_method,
                'payment_method_display': item.get_payment_method_display(),
                'payment_status': item.payment_status,
                'payment_status_display': item.get_payment_status_display(),
                'tracking_status': item.tracking_status,
                'tracking_status_display': item.get_tracking_status_display(),
                'tracking_number': item.tracking_number,
                'dispatch_date': item.dispatch_date.strftime('%Y-%m-%d %H:%M') if item.dispatch_date else None,
                'estimated_delivery': item.estimated_delivery.strftime('%Y-%m-%d') if item.estimated_delivery else None,
                'has_dispute': item.has_dispute,
                'dispute': dispute_info,
                'tracking_history': tracking_history,
            })

        # Check for pending delivery confirmations
        pending_confirmation = DeliveryConfirmation.objects.filter(
            order=order, buyer=request.user, is_submitted=False
        ).first()

        # Items awaiting buyer confirmation
        items_awaiting_confirmation = []
        if pending_confirmation:
            items_awaiting_confirmation = list(
                order.items.filter(
                    tracking_status='delivered_by_seller'
                ).values_list('id', flat=True)
            )

        return Response({
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'status': order.status,
                'status_display': order.get_status_display(),
                'total_amount': str(order.total_amount),
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            },
            'sellers': list(sellers_map.values()),
            'has_pending_confirmation': pending_confirmation is not None,
            'items_awaiting_confirmation': items_awaiting_confirmation,
        })

    except Exception as e:
        logger.error(f"Error fetching buyer order tracking: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════
#  BUYER — DELIVERY CONFIRMATION & DISPUTE SUBMISSION
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='login_user')
def delivery_confirmation_page(request, order_id):
    """Render the delivery confirmation / dispute page."""
    return render(request, 'delivery_confirmation.html', {'order_id': order_id})


@login_required(login_url='login_user')
@api_view(['GET'])
def get_delivery_confirmation_items(request, order_id):
    """
    Get items that the seller has marked as delivered and need buyer confirmation.
    """
    try:
        order = get_object_or_404(Order, id=order_id, buyer=request.user)

        items = order.items.filter(
            tracking_status='delivered_by_seller'
        ).select_related('product', 'seller')

        items_data = [{
            'item_id': item.id,
            'product_name': item.product.name,
            'product_image': item.product.image_display_url or item.product.image_url,
            'quantity': item.quantity,
            'price': str(item.price),
            'subtotal': str(item.subtotal),
            'seller_email': item.seller.email,
            'payment_method': item.payment_method,
            'payment_method_display': item.get_payment_method_display(),
            'payment_status': item.payment_status,
        } for item in items]

        return Response({
            'order_number': order.order_number,
            'order_id': order.id,
            'items': items_data,
        })

    except Exception as e:
        logger.error(f"Error fetching confirmation items: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)



def _release_escrow_for_item(order, order_item):
    """
    Tell the payment app to release the seller's reserved (escrow) funds
    for a confirmed-delivered order item.

    Called after buyer confirms delivery in submit_delivery_confirmation.
    Failure is non-blocking — logs a warning but does not roll back the
    delivery confirmation.
    """
    try:
        url = (
            f"{FAIR_CASHIER_URL}"
            f"/payment/{order.fair_cashier_request_id}"
            f"/release-seller-funds/shopping-item/{order_item.id}/"
        )
        resp = http_requests.post(
            url,
            json={'api_key': FAIR_CASHIER_API_KEY},
            headers={'Content-Type': 'application/json'},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get('success'):
            logger.info(
                f"✅ Escrow released for order item {order_item.id} "
                f"(order {order.order_number})"
            )
        elif resp.status_code == 404:
            # Item may have already been released (idempotent)
            logger.info(
                f"ℹ️ release_escrow: item {order_item.id} already released or not in escrow"
            )
        else:
            logger.warning(
                f"⚠️ release_escrow failed for item {order_item.id}: "
                f"{resp.status_code} — {resp.text[:200]}"
            )
    except http_requests.exceptions.RequestException as e:
        logger.warning(f"⚠️ release_escrow network error for item {order_item.id}: {e}")
    except Exception as e:
        logger.error(f"❌ release_escrow unexpected error: {e}", exc_info=True)


@login_required(login_url='login_user')
@api_view(['POST'])
def submit_delivery_confirmation(request, order_id):
    """
    Buyer submits delivery confirmation with per-item approval or dispute.

    POST body: {
        "items": [
            {
                "item_id": 1,
                "confirmed": true       // buyer confirms receipt, no complaint
            },
            {
                "item_id": 2,
                "confirmed": false,      // buyer disputes
                "complaint_type": "damaged",
                "description": "Box was crushed and item broken"
            }
        ]
    }
    """
    try:
        order = get_object_or_404(Order, id=order_id, buyer=request.user)
        items_data = request.data.get('items', [])

        if not items_data:
            return Response({'error': 'No items provided'}, status=400)

        disputes_created = []
        confirmed_count = 0

        with db_transaction.atomic():
            for item_data in items_data:
                item_id = item_data.get('item_id')
                confirmed = item_data.get('confirmed', True)

                order_item = get_object_or_404(
                    OrderItem, id=item_id, order=order
                )

                if confirmed:
                    # Buyer confirms delivery
                    order_item.tracking_status      = 'delivered'
                    order_item.delivery_confirmed_at = timezone.now()
                    order_item.save()

                    OrderItemTracking.objects.create(
                        order_item=order_item,
                        status='delivered',
                        notes='Buyer confirmed delivery — no issues.',
                        updated_by_role='buyer',
                        updated_by=request.user,
                    )
                    confirmed_count += 1

                    # Release seller's escrowed funds → free balance
                    # 'escrowed' = buyer paid, funds held in seller's reserved wallet.
                    # 'paid'     = already released (idempotent call is safe).
                    # 'deposited'= old buyer-reserve flow (no seller escrow to release).
                    if (
                        order_item.payment_method == 'online'
                        and order_item.payment_status == 'escrowed'
                        and order.fair_cashier_request_id
                    ):
                        _release_escrow_for_item(order, order_item)

                else:
                    # Buyer disputes this item
                    complaint_type = item_data.get('complaint_type', 'other')
                    description = item_data.get('description', '')

                    order_item.tracking_status = 'disputed'
                    order_item.has_dispute = True
                    order_item.save()

                    # Create dispute record
                    dispute = OrderDispute.objects.create(
                        order_item=order_item,
                        order=order,
                        buyer=request.user,
                        seller=order_item.seller,
                        complaint_type=complaint_type,
                        description=description,
                        is_online_payment=(
                            order_item.payment_method == 'online'
                            and order_item.payment_status in ('paid', 'escrowed')
                        ),
                    )

                    OrderItemTracking.objects.create(
                        order_item=order_item,
                        status='disputed',
                        notes=f'Buyer filed dispute: {dispute.get_complaint_type_display()}',
                        updated_by_role='buyer',
                        updated_by=request.user,
                    )

                    # If online-paid item, forward dispute to payment app
                    if dispute.needs_payment_app:
                        _forward_dispute_to_payment_app(dispute)

                    disputes_created.append(dispute.dispute_id)

            # Mark delivery confirmation as submitted
            dc = DeliveryConfirmation.objects.filter(
                order=order, buyer=request.user, is_submitted=False
            ).first()
            if dc:
                dc.is_submitted = True
                dc.submitted_at = timezone.now()
                dc.save()

            # Update overall order status
            _update_order_status(order)

        return Response({
            'success': True,
            'confirmed_count': confirmed_count,
            'disputes_created': disputes_created,
            'message': f'{confirmed_count} items confirmed, {len(disputes_created)} disputes filed.',
        })

    except Exception as e:
        logger.error(f"Error submitting delivery confirmation: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════
#  BUYER — PENDING DELIVERY NOTIFICATIONS (for popup)
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='login_user')
@api_view(['GET'])
def check_pending_deliveries(request):
    """
    Check if the logged-in buyer has any orders with items marked
    as delivered_by_seller that need confirmation.
    Used for the pop-up notification on the buyer's side.
    """
    try:
        pending = DeliveryConfirmation.objects.filter(
            buyer=request.user,
            is_submitted=False,
        ).select_related('order')

        notifications = []
        for dc in pending:
            items_count = dc.order.items.filter(
                tracking_status='delivered_by_seller'
            ).count()
            if items_count > 0:
                notifications.append({
                    'order_id': dc.order.id,
                    'order_number': dc.order.order_number,
                    'items_count': items_count,
                    'created_at': dc.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                })

        return Response({
            'has_pending': len(notifications) > 0,
            'notifications': notifications,
        })

    except Exception as e:
        logger.error(f"Error checking pending deliveries: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


# ═══════════════════════════════════════════════════════════════════════════
#  PAYMENT APP DISPUTE SYNC — WEBHOOK RECEIVER
# ═══════════════════════════════════════════════════════════════════════════
@csrf_exempt
@require_http_methods(["POST"])
def dispute_status_webhook(request):
    """
    Webhook endpoint for the payment app to sync dispute status updates
    back to the shopping app.

    Called by the payment app when:
      - dispute status changes (under_review, escalated, etc.)
      - refund is processed
      - dispute is resolved

    Payload: {
        "api_key": "...",
        "shopping_dispute_id": 123,
        "payment_dispute_id": 456,
        "status": "resolved_with_refund",
        "payment_status": "refunded",
        "refund_amount": "5000.00",
        "admin_notes": "Refund approved and processed",
        "resolved_at": "2026-02-16T10:30:00Z"
    }
    """
    try:
        data = json.loads(request.body)

        # Verify API key
        api_key = data.get('api_key')
        if api_key != FAIR_CASHIER_API_KEY:
            return JsonResponse({'error': 'Invalid API key'}, status=403)

        shopping_dispute_id = data.get('shopping_dispute_id')
        payment_status = data.get('payment_status', '')
        dispute_status = data.get('status', '')
        refund_amount = data.get('refund_amount')
        admin_notes = data.get('admin_notes', '')
        resolved_at = data.get('resolved_at')

        dispute = get_object_or_404(OrderDispute, dispute_id=shopping_dispute_id)

        with db_transaction.atomic():
            dispute.payment_app_status = payment_status
            dispute.status = dispute_status

            if admin_notes:
                dispute.admin_notes = admin_notes

            if refund_amount:
                dispute.refund_amount = Decimal(refund_amount)
                dispute.refund_processed_at = timezone.now()

            if resolved_at:
                from datetime import datetime
                dispute.resolved_at = datetime.fromisoformat(resolved_at.replace('Z', '+00:00'))

            dispute.save()

            # ── Reset OrderItem tracking_status when dispute is resolved ──
            # When the buyer filed the dispute, tracking_status was set to
            # 'disputed'. Now that the dispute is resolved, move the item
            # back to 'reviewed' so the seller can resume the normal
            # tracking flow (reviewed → confirmed → packed → …).
            RESOLVED_STATUSES = ('resolved_with_refund', 'resolved_without_refund')
            order_item = dispute.order_item
            if dispute_status in RESOLVED_STATUSES and order_item.tracking_status == 'disputed':
                order_item.tracking_status = 'reviewed'
                order_item.save()

                OrderItemTracking.objects.create(
                    order_item=order_item,
                    status='reviewed',
                    notes=f'Dispute {dispute_status.replace("_", " ")} — item returned to tracking flow for seller review.',
                    updated_by_role='system',
                )

            # Log the payment platform update
            OrderItemTracking.objects.create(
                order_item=dispute.order_item,
                status=f'dispute_{dispute_status}',
                notes=f'Payment platform update: {payment_status}. {admin_notes}',
                updated_by_role='system',
            )

            # Check if all disputes on the order are resolved
            _update_order_status(dispute.order)

        logger.info(f"✅ Dispute #{shopping_dispute_id} synced from payment app: {payment_status}")

        return JsonResponse({
            'success': True,
            'message': 'Dispute status synced',
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in dispute sync webhook: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

# ═══════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _check_and_create_delivery_confirmation(order, seller_user):
    """
    When a seller marks items as delivered_by_seller, create a
    DeliveryConfirmation record for the buyer (if not already existing).
    """
    # Check if there are items marked as delivered by seller
    delivered_items = order.items.filter(tracking_status='delivered_by_seller')
    if not delivered_items.exists():
        return

    # Create or get existing unsubmitted confirmation
    dc, created = DeliveryConfirmation.objects.get_or_create(
        order=order,
        buyer=order.buyer,
        is_submitted=False,
    )
    if created:
        logger.info(
            f"📦 Delivery confirmation created for order {order.order_number}, "
            f"buyer {order.buyer.email}"
        )


def _update_order_status(order):
    """
    Recalculate and update the overall order status based on item statuses.

    Rules:
      - If any item has an unresolved dispute → 'escalated'
      - If all items are confirmed delivered → 'completed'
      - If some items delivered, some not → 'partially_delivered'
      - If all items delivered_by_seller but none confirmed → 'delivered'
      - Otherwise → keep current status (processing/pending)
    """
    all_items = order.items.all()
    total = all_items.count()
    if total == 0:
        return

    # Count statuses
    confirmed_delivered = all_items.filter(tracking_status='delivered').count()
    delivered_by_seller = all_items.filter(tracking_status='delivered_by_seller').count()
    disputed_resolved = all_items.filter(
        tracking_status='disputed',
        has_dispute=True,
        dispute__status__in=['resolved_with_refund', 'resolved_without_refund']
    ).count()

    effective_complete = confirmed_delivered + disputed_resolved

    if effective_complete == total:
        order.status = 'completed'
    elif effective_complete > 0 and effective_complete < total:
        order.status = 'partially_delivered'
    elif confirmed_delivered > 0 or delivered_by_seller > 0:
        if delivered_by_seller > 0 and confirmed_delivered == 0:
            order.status = 'delivered'
        else:
            order.status = 'partially_delivered'
    # else: keep current status

    order.save()


def _forward_dispute_to_payment_app(dispute):
    """
    Forward an online-payment dispute to the Fair Cashier payment app.
    Creates a Dispute record in the payment app via API.
    """
    try:
        buyer = dispute.buyer
        seller = dispute.seller
        order_item = dispute.order_item

        payload = {
            'api_key': FAIR_CASHIER_API_KEY,
            'shopping_dispute_id': dispute.dispute_id,
            'buyer_email': buyer.email,
            'buyer_phone': str(buyer.phonenumber) if buyer.phonenumber else None,
            'seller_email': seller.email,
            'seller_phone': str(seller.phonenumber) if seller.phonenumber else None,
            'order_number': dispute.order.order_number,
            'item_description': order_item.product.name,
            'amount': str(order_item.subtotal),
            'reason': dispute.complaint_type,
            'reason_display': dispute.get_complaint_type_display(),
            'description': dispute.description or '',
            'metadata': {
                'order_id': dispute.order.id,
                'order_item_id': order_item.id,
                'product_name': order_item.product.name,
                'quantity': order_item.quantity,
            }
        }

        response = http_requests.post(
            f"{FAIR_CASHIER_URL}/api/dispute/create-from-shopping/",
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=15
        )

        if response.status_code in [200, 201]:
            resp_data = response.json()
            dispute.payment_app_dispute_id = resp_data.get('dispute_id')
            dispute.status = 'submitted'
            dispute.payment_app_status = resp_data.get('status', 'To Be Decided')
            dispute.save()
            logger.info(
                f"✅ Dispute #{dispute.dispute_id} forwarded to payment app "
                f"→ Payment dispute #{dispute.payment_app_dispute_id}"
            )
        else:
            logger.error(
                f"❌ Failed to forward dispute #{dispute.dispute_id} to payment app: "
                f"{response.status_code} - {response.text}"
            )

    except http_requests.exceptions.RequestException as e:
        logger.error(f"❌ Connection error forwarding dispute: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Error forwarding dispute: {str(e)}", exc_info=True)