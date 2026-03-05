from django.urls import path
from . import views_balance_proof

balance_proof_urlpatterns = [
    
    path('order/<str:order_id>/balance-status/', views_balance_proof.order_balance_status, name='order_balance_status'),
    path('order/<str:order_id>/balance-refresh/', views_balance_proof.refresh_balance_status, name='refresh_balance_status'),

]