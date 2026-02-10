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


# ============= SELLER REGISTRATION WITH FAIR CASHIER =============

@login_required
@require_http_methods(["POST"])
def register_seller_with_fc(request):
    """
    Register seller with Fair Cashier payment system
    
    This is called when seller doesn't have a Fair Cashier account
    Redirects to Fair Cashier PIN setup
    """
    try:
        seller_email = request.user.email
        
        # Generate access token for registration flow
        access_token = generate_seller_access_token(seller_email)
        
        # Build PIN setup URL
        pin_setup_url = (
            f"{FAIR_CASHIER_URL}/pin-setup/"
            f"?email={seller_email}"
            f"&role=seller"
            f"&platform_key={FAIR_CASHIER_API_KEY}"
            f"&token={access_token}"
            f"&return={FAIR_CASHIER_URL}/payment/seller-dashboard/"
        )
        
        return JsonResponse({
            'success': True,
            'redirect_url': pin_setup_url
        })
        
    except Exception as e:
        logger.error(f"❌ Error initiating FC registration: {str(e)}")
        return JsonResponse({
            'error': 'Failed to initiate registration'
        }, status=500)


# ============= ADMIN: VIEW PENDING CASHOUTS =============

@login_required
def admin_view_pending_cashouts(request):
    """
    Platform admin view for pending seller cashout requests
    
    Only accessible by users with 'admin' or 'superadmin' role
    """
    # Verify admin access
    if request.user.role not in ['admin', 'superadmin']:
        logger.warning(f"⚠️ Non-admin tried to access cashouts: {request.user.email}")
        return redirect('home')
    
    return render(request, 'admin_pending_cashouts.html')


@login_required
@require_http_methods(["GET"])
def get_pending_cashouts(request):
    """
    Get list of pending cashout requests for this platform
    
    This would query Fair Cashier API for pending cashouts
    related to this platform's sellers
    """
    try:
        # Verify admin access
        if request.user.role not in ['admin', 'superadmin']:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Call Fair Cashier API to get pending cashouts
        response = requests.get(
            f"{FAIR_CASHIER_URL}/api/admin/pending-cashouts/",
            params={
                'api_key': FAIR_CASHIER_API_KEY
            },
            timeout=10
        )
        
        if response.status_code == 200:
            return JsonResponse(response.json())
        else:
            logger.error(f"❌ Failed to fetch cashouts: {response.status_code}")
            return JsonResponse({
                'error': 'Failed to fetch cashouts'
            }, status=500)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error fetching cashouts: {str(e)}")
        return JsonResponse({
            'error': 'Connection error'
        }, status=503)


@login_required
@require_http_methods(["POST"])
def approve_cashout(request):
    """
    Admin approves cashout and triggers disbursement
    
    POST body:
        - transaction_id: UUID of cashout transaction
        - seller_email: Seller's email
        - amount: Cashout amount
        - phone_number: Mobile money number
    """
    try:
        import json
        
        # Verify admin access
        if request.user.role not in ['admin', 'superadmin']:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        data = json.loads(request.body)
        transaction_id = data.get('transaction_id')
        seller_email = data.get('seller_email')
        amount = data.get('amount')
        phone_number = data.get('phone_number')
        
        if not all([transaction_id, seller_email, amount, phone_number]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        # Call Fair Cashier API to approve cashout
        response = requests.post(
            f"{FAIR_CASHIER_URL}/api/admin/approve-cashout/",
            json={
                'api_key': FAIR_CASHIER_API_KEY,
                'transaction_id': transaction_id,
                'admin_email': request.user.email,
                'approved': True
            },
            headers={'Content-Type': 'application/json'},
            timeout=15
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            
            logger.info(f"✅ Cashout approved: {transaction_id} by {request.user.email}")
            
            return JsonResponse({
                'success': True,
                'message': 'Cashout approved and processed',
                'transaction_id': transaction_id
            })
        else:
            logger.error(f"❌ Cashout approval failed: {response.text}")
            return JsonResponse({
                'error': 'Failed to approve cashout',
                'details': response.text
            }, status=500)
            
    except Exception as e:
        logger.error(f"❌ Error approving cashout: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Failed to process approval'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def reject_cashout(request):
    """
    Admin rejects cashout request
    
    POST body:
        - transaction_id: UUID of cashout transaction
        - reason: Rejection reason
    """
    try:
        import json
        
        # Verify admin access
        if request.user.role not in ['admin', 'superadmin']:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        data = json.loads(request.body)
        transaction_id = data.get('transaction_id')
        reason = data.get('reason', 'Rejected by admin')
        
        if not transaction_id:
            return JsonResponse({'error': 'Transaction ID required'}, status=400)
        
        # Call Fair Cashier API to reject cashout
        response = requests.post(
            f"{FAIR_CASHIER_URL}/api/admin/reject-cashout/",
            json={
                'api_key': FAIR_CASHIER_API_KEY,
                'transaction_id': transaction_id,
                'admin_email': request.user.email,
                'reason': reason
            },
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"⚠️ Cashout rejected: {transaction_id} by {request.user.email}")
            
            return JsonResponse({
                'success': True,
                'message': 'Cashout rejected',
                'transaction_id': transaction_id
            })
        else:
            logger.error(f"❌ Cashout rejection failed: {response.text}")
            return JsonResponse({
                'error': 'Failed to reject cashout'
            }, status=500)
            
    except Exception as e:
        logger.error(f"❌ Error rejecting cashout: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Failed to process rejection'
        }, status=500)