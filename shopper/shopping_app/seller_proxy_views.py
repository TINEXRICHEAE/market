# shopping_app/seller_proxy_views.py
"""
E-Commerce Shopping App - Seller Fair Cashier Proxy Views (WITH DEBUGGING)
Handles seller access to Fair Cashier payment system
"""

import requests
import hashlib
import time
import logging
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

# Fair Cashier Configuration
FAIR_CASHIER_URL = getattr(settings, 'FAIR_CASHIER_API_URL', 'http://localhost:8001')
FAIR_CASHIER_API_KEY = getattr(settings, 'FAIR_CASHIER_API_KEY', '')


# ============= HELPER FUNCTIONS =============

def generate_seller_access_token(seller_email):
    """
    Generate secure access token for seller to access Fair Cashier
    
    Token format: hash(api_key:email:timestamp):timestamp
    This MUST match Fair Cashier's verification logic exactly
    
    Args:
        seller_email: Seller's email
    
    Returns:
        str: Access token (format: hash:timestamp)
    """
    timestamp = str(int(time.time()))
    
    # ✅ CRITICAL: This string MUST match Fair Cashier's verification
    # Format: api_key:email:timestamp (NO SECRET KEY)
    string = f"{FAIR_CASHIER_API_KEY}:{seller_email}:{timestamp}"
    token = hashlib.sha256(string.encode()).hexdigest()[:32]
    
    token_string = f"{token}:{timestamp}"
    
    logger.info(f"✅ Generated seller access token for {seller_email}")
    logger.debug(f"String to hash: {string}")
    logger.debug(f"Generated token: {token}")
    logger.debug(f"Timestamp: {timestamp}")
    logger.debug(f"Full token string: {token_string}")
    
    return token_string


# ============= SELLER FINANCES PAGE =============

@login_required
def seller_finances_page(request):
    """
    Seller finances page with Fair Cashier iframe
    
    Generates access token and embeds Fair Cashier seller dashboard
    """
    # Verify user is seller
    if request.user.role != 'seller':
        logger.warning(f"⚠️ Non-seller tried to access finances: {request.user.email}")
        return redirect('home')
    
    seller_email = request.user.email
    
    # Generate access token
    access_token = generate_seller_access_token(seller_email)
    
    # Build Fair Cashier iframe URL with auth parameters
    iframe_url = (
        f"{FAIR_CASHIER_URL}/payment/seller-dashboard/"
        f"?email={seller_email}"
        f"&platform_key={FAIR_CASHIER_API_KEY}"
        f"&token={access_token}"
    )
    
    context = {
        'iframe_url': iframe_url,
        'seller_email': seller_email,
        'fair_cashier_domain': FAIR_CASHIER_URL
    }
    
    logger.info(f"📊 Seller finances page loaded for {seller_email}")
    logger.debug(f"Iframe URL: {iframe_url}")
    
    return render(request, 'seller_finances.html', context)


# ============= CHECK SELLER FAIR CASHIER STATUS =============

@login_required
@require_http_methods(["GET"])
def check_seller_fc_status(request):
    """
    Check if current seller is registered with Fair Cashier
    
    Returns:
        - registered: bool
        - has_wallet: bool
        - has_pin: bool
    """
    try:
        seller_email = request.user.email
        
        # Call Fair Cashier API
        response = requests.post(
            f"{FAIR_CASHIER_URL}/api/check-sellers/",
            json={
                'api_key': FAIR_CASHIER_API_KEY,
                'seller_emails': [seller_email]
            },
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            results = response.json().get('results', {})
            seller_data = results.get(seller_email, {})
            
            return JsonResponse({
                'registered': seller_data.get('registered', False),
                'has_wallet': seller_data.get('has_wallet', False),
                'has_pin': seller_data.get('has_pin', False),
                'email': seller_email
            })
        else:
            logger.error(f"❌ Fair Cashier check failed: {response.status_code}")
            return JsonResponse({
                'registered': False,
                'has_wallet': False,
                'has_pin': False,
                'error': 'Failed to check status'
            }, status=500)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error checking seller FC status: {str(e)}")
        return JsonResponse({
            'registered': False,
            'has_wallet': False,
            'has_pin': False,
            'error': 'Connection error'
        }, status=503)
