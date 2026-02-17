# File: shopping_app/order_urls.py   (NEW FILE)

from django.urls import path
from . import order_views

order_urlpatterns = [

    # ── SELLER: Order Management ──
    path('seller/orders/',
         order_views.seller_orders_page,
         name='seller_orders'),

    path('api/seller/orders/',
         order_views.get_seller_orders,
         name='api_seller_orders'),

    path('seller/order/<int:order_id>/',
         order_views.seller_order_detail_page,
         name='seller_order_detail'),

    path('api/seller/order/<int:order_id>/',
         order_views.get_seller_order_detail,
         name='api_seller_order_detail'),

    # Seller updates tracking status on a single item
    path('api/seller/order-item/<int:item_id>/update-tracking/',
         order_views.update_order_item_tracking,
         name='api_update_item_tracking'),

    # Seller bulk-updates tracking for multiple items in an order
    path('api/seller/order/<int:order_id>/bulk-update-tracking/',
         order_views.bulk_update_tracking,
         name='api_bulk_update_tracking'),


    # ── BUYER: Order Tracking ──
    path('order/<int:order_id>/tracking/',
         order_views.buyer_order_tracking_page,
         name='buyer_order_tracking'),

    path('api/order/<int:order_id>/tracking/',
         order_views.get_buyer_order_tracking,
         name='api_buyer_order_tracking'),


    # ── BUYER: Delivery Confirmation & Disputes ──
    path('order/<int:order_id>/confirm-delivery/',
         order_views.delivery_confirmation_page,
         name='delivery_confirmation'),

    path('api/order/<int:order_id>/confirmation-items/',
         order_views.get_delivery_confirmation_items,
         name='api_delivery_confirmation_items'),

    path('api/order/<int:order_id>/submit-confirmation/',
         order_views.submit_delivery_confirmation,
         name='api_submit_delivery_confirmation'),


    # ── BUYER: Pending Delivery Notifications (for popup) ──
    path('api/pending-deliveries/',
         order_views.check_pending_deliveries,
         name='api_pending_deliveries'),


    # ── WEBHOOK: Payment App Dispute Status Sync ──
    path('api/webhook/dispute-status/',
         order_views.dispute_status_webhook,
         name='dispute_status_webhook'),
]