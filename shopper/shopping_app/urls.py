from django.urls import path
from . import views
from shopping_app.proxy_urls import proxy_urlpatterns

urlpatterns = [
    # === User Authentication ===
    path('register_user/', views.register_user, name='register_user'),
    path('login_user/', views.login_user, name='login_user'),
    path('check_auth/', views.check_auth, name='check_auth'),
    path('logout_user/', views.logout_user, name='logout_user'),
    path('user_profile/', views.user_profile, name='user_profile'),
    path('delete_account/', views.delete_account, name='delete_account'),

    # === CSRF Token (Required for all POST/PUT/DELETE) ===
    path('api/csrf/', views.get_csrf_token, name='get_csrf'),

    # === Main Pages ===
    path('', views.home, name='home'),

    # === Product Views ===
    path('products/', views.product_list, name='product_list'),
    path('api/products/', views.get_products, name='get_products'),
    path('products/<int:product_id>/',
         views.product_detail, name='product_detail'),
    path('api/products/<int:product_id>/',
         views.get_product_detail, name='get_product_detail'),

    # === Cart Views ===
    path('cart/', views.view_cart, name='view_cart'),
    path('api/cart/', views.get_cart, name='get_cart'),
    path('api/cart/add/', views.add_to_cart, name='add_to_cart'),
    path('api/cart/update/<int:item_id>/',
         views.update_cart_item, name='update_cart_item'),
    path('api/cart/remove/<int:item_id>/',
         views.remove_from_cart, name='remove_from_cart'),

    # === Wishlist Views ===
    path('wishlist/', views.view_wishlist, name='view_wishlist'),
    path('api/wishlist/', views.get_wishlist, name='get_wishlist'),
    path('api/wishlist/toggle/', views.toggle_wishlist, name='toggle_wishlist'),
    path('api/wishlist/remove/<int:wishlist_id>/',
         views.remove_from_wishlist, name='remove_from_wishlist'),

    # === Checkout & Orders ===
    path('orders/', views.view_orders, name='view_orders'),
    path('api/orders/', views.get_orders, name='get_orders'),
    path('orders/<int:order_id>/', views.view_order_detail,
         name='view_order_detail'),
    path('api/orders/<int:order_id>/',
         views.get_order_detail, name='get_order_detail'),
    path('checkout/', views.checkout, name='checkout'),
    path('api/checkout/process/', views.process_checkout, name='process_checkout'),

    # === Seller Dashboard (Non-API) ===
    path('seller/dashboard/', views.seller_dashboard, name='seller_dashboard'),
    path('seller/products/', views.seller_products, name='seller_products'),
    path('seller/products/add/', views.seller_add_product,
         name='seller_add_product'),
    path('seller/products/edit/<int:product_id>/',
         views.seller_edit_product, name='seller_edit_product'),
    path('seller/cashout/', views.seller_cashout, name='seller_cashout'),

    # === Seller API Endpoints ===
    path('api/seller/sales/', views.get_seller_sales, name='get_seller_sales'),
    path('api/seller/products/', views.get_seller_products,
         name='get_seller_products'),
    path('api/seller/products/create/',
         views.create_product, name='create_product'),
    path('api/seller/products/<int:product_id>/',
         views.get_seller_product_detail, name='get_seller_product_detail'),
    path('api/seller/products/<int:product_id>/update/',
         views.update_product, name='update_product'),
    path('api/seller/products/<int:product_id>/delete/',
         views.delete_product, name='delete_product'),

    # === Seller Balance & Cash-Out API ===
    path('api/seller/balance/', views.get_seller_balance,
         name='get_seller_balance'),
    path('api/seller/cashout/request/',
         views.request_cashout, name='request_cashout'),
    path('api/seller/cashout/history/',
         views.get_cashout_history, name='get_cashout_history'),

    # === Optional: Categories (used by seller form) ===
    path('api/categories/', views.get_categories, name='get_categories'),

    # Enhanced User Profile Management
    path('api/user/details/', views.get_user_details, name='get_user_details'),
    path('api/user/update-role/', views.update_user_role, name='update_user_role'),
    path('api/user/update-password/', views.update_user_password,
         name='update_user_password'),

    path('payment/select/', views.payment_selection_page, name='payment_selection_page'),
    path('api/process-payment-selection/', views.process_payment_selection, name='process_payment_selection'),

    path('api/orders/<int:order_id>/retry-payment/', 
         views.retry_online_payment, 
         name='retry_online_payment'),

     path('api/orders/<int:order_id>/pay-selected-items/', 
     views.retry_selected_items_payment, 
     name='retry_selected_items_payment'),
] + proxy_urlpatterns
