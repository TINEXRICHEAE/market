# shopping_app/seller_proxy_urls.py
"""
E-Commerce Shopping App - Seller Fair Cashier Proxy URLs
Routes for seller access to Fair Cashier payment system
"""

from django.urls import path
from . import seller_proxy_views

seller_proxy_urlpatterns = [
    # Seller finances page (iframe container)
    path('seller/finances/', 
         seller_proxy_views.seller_finances_page, 
         name='seller_finances'),
    
    # Check seller Fair Cashier status
    path('api/seller/fc-status/', 
         seller_proxy_views.check_seller_fc_status, 
         name='check_seller_fc_status'),
    
    # Register seller with Fair Cashier
    path('api/seller/fc-register/', 
         seller_proxy_views.register_seller_with_fc, 
         name='register_seller_fc'),
    
    # Admin: Pending cashouts
    path('admin/cashouts/', 
         seller_proxy_views.admin_view_pending_cashouts, 
         name='admin_pending_cashouts'),
    
    path('api/admin/cashouts/pending/', 
         seller_proxy_views.get_pending_cashouts, 
         name='get_pending_cashouts'),
    
    path('api/admin/cashouts/approve/', 
         seller_proxy_views.approve_cashout, 
         name='approve_cashout'),
    
    path('api/admin/cashouts/reject/', 
         seller_proxy_views.reject_cashout, 
         name='reject_cashout'),
]
