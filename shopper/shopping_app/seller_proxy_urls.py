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
    
    
]
