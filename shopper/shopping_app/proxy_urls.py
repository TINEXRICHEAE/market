# shopping_app/proxy_urls.py
"""
URL Configuration for Fair Cashier Payment Gateway Integration
All routes related to Fair Cashier payment processing
"""

from django.urls import path
from . import proxy_views

# Fair Cashier integration URLs
proxy_urlpatterns = [
    # Seller verification
    path('api/fair-cashier/check-sellers/', 
         proxy_views.check_sellers_registration, 
         name='fc_check_sellers'),
    
    # Payment request creation
    path('api/fair-cashier/payment/create/', 
         proxy_views.create_payment_request, 
         name='fc_create_payment'),
    
    # Payment iframe container
    path('payment/process/<uuid:request_id>/', 
         proxy_views.payment_iframe_proxy, 
         name='fc_payment_iframe'),
    
    # Payment callback from Fair Cashier (webhook)
    path('api/fair-cashier/payment/callback/', 
         proxy_views.payment_callback, 
         name='fc_payment_callback'),
    
    # Return from Fair Cashier
    path('payment/return/', 
         proxy_views.payment_return, 
         name='fc_payment_return'),
    
    # Buyer status check (for Fair Cashier)
    path('api/fair-cashier/check-buyer/', 
         proxy_views.check_buyer_fair_cashier_status, 
         name='fc_check_buyer'),
    path('api/webhook/payment-status/', proxy_views.payment_status_webhook, name='payment_status_webhook'),
]