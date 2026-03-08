# shopping_app/urls_balance_proof.py
"""
Shopping App — Balance Proof URLs

Endpoints for seller-facing buyer balance proof tier display.
Shopping App VERIFIES proofs (via Strapi /api/verify-balance-proof).
Payment App GENERATES proofs (via Strapi /api/generate-balance-proof).
"""

from django.urls import path
from . import views_balance_proof

balance_proof_urlpatterns = [
    # Seller views buyer's balance tier for an order
    path('api/buyer-balance-proof/',
         views_balance_proof.api_buyer_balance_proof,
         name='api_buyer_balance_proof'),

    # Seller triggers a fresh proof from Payment App
    path('api/buyer-balance-proof/refresh/',
         views_balance_proof.api_buyer_balance_proof_refresh,
         name='api_buyer_balance_proof_refresh'),
]