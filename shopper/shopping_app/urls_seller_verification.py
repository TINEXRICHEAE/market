from django.urls import path
from .views_seller_verification import (
    seller_kyc_submit,
    seller_kyc_status,
    api_seller_verification_status,
    api_seller_kyc_status,
    internal_seller_kyc_data,
    api_buyer_balance_proof,
    api_buyer_balance_proof_refresh,
)
from . import views_zkp

seller_verification_urlpatterns = [
    # ── Seller KYC submission + status ───────────────────────────────
    path('seller/kyc/', seller_kyc_submit, name='seller_kyc_submit'),
    path('seller/kyc/status/', seller_kyc_status, name='seller_kyc_status'),

    # ── Buyer-facing seller verification badge (AJAX) ────────────────
    path('api/seller-verification-status/<int:seller_id>/',
         api_seller_verification_status, name='api_seller_verification_status'),

    # ── Navbar badge (seller's own lightweight status) ───────────────
    path('api/seller/kyc-status/', api_seller_kyc_status, name='api_seller_kyc_status'),

    # ── Internal: payment app fetches KYC data ───────────────────────
    path('internal/seller-kyc/<str:seller_email>/',
         internal_seller_kyc_data, name='internal_seller_kyc_data'),

    # ── ZKP Registration (Shopping App registers sellers) ────────────
    path('seller/zkp/register/', views_zkp.seller_zkp_register, name='seller_zkp_register'),
    path('seller/zkp/regenerate-proof/', views_zkp.seller_zkp_regenerate_proof, name='seller_zkp_regenerate_proof'),
    path('seller/zkp-status/<str:seller_email>/', views_zkp.seller_zkp_status, name='seller_zkp_status'),
    path('internal/seller-zkp-proof/<str:seller_email>/', views_zkp.internal_seller_zkp_proof, name='internal_seller_zkp_proof'),

    # ── Buyer balance proof (seller-facing tier display) ─────────────
    path('api/buyer-balance-proof/', api_buyer_balance_proof, name='api_buyer_balance_proof'),
    path('api/buyer-balance-proof/refresh/', api_buyer_balance_proof_refresh, name='api_buyer_balance_proof_refresh'),
]