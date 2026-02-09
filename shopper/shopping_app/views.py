import logging
import hashlib
import time
import json
import urllib.parse
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from phonenumber_field.phonenumber import to_python
from .models import (
    Users, Product, Category, Cart, CartItem,
    Wishlist, Order, OrderItem, SellerPayment, CashOut
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.middleware.csrf import get_token
import requests
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.db import transaction
from django.db.models import Sum, Q, Count
import os
from django.core.files.storage import FileSystemStorage
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.contrib.auth import update_session_auth_hash

logger = logging.getLogger(__name__)


def home(request):
    return render(request, 'home.html')


def register_user(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        register_as_seller = request.POST.get('register_as_seller') == 'on'
        role = 'seller' if register_as_seller else 'buyer'

        if not email or not password1 or not password2:
            return JsonResponse({'error': 'Email and password are required'}, status=400)

        if password1 != password2:
            return JsonResponse({'error': 'Passwords do not match'}, status=400)

        if Users.objects.filter(email=email).exists():
            return JsonResponse({'error': 'Email already registered'}, status=400)

        user = Users.objects.create_user(
            email=email,
            password=password1,
            role=role,
            is_staff=(role == 'admin' or role == 'superadmin'),
            is_superuser=(role == 'superadmin'),
        )

        return JsonResponse({
            'message': 'User registered successfully',
            'user_id': user.id,
            'email': user.email,
            'role': user.role
        }, status=201)

    return render(request, 'signup.html')


def login_user(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        if not email or not password:
            return JsonResponse({'error': 'Email and password are required'}, status=400)

        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({
                'message': 'Login successful',
                'user_id': user.id,
                'email': user.email,
                'role': user.role
            }, status=200)
        else:
            return JsonResponse({'error': 'Invalid email or password'}, status=401)

    return render(request, 'login.html')


def check_auth(request):
    logger.info(f"User authenticated: {request.user.is_authenticated}")
    return JsonResponse({'is_authenticated': request.user.is_authenticated})


def logout_user(request):
    if request.method == 'POST':
        logout(request)
        return JsonResponse({'message': 'Logout successful'}, status=200)
    return JsonResponse({'error': 'Invalid request method'}, status=400)


@login_required(login_url='login_user')
def user_profile(request):
    if request.method == 'GET':
        try:
            user_email = request.user.email
            user_phonenumber = str(
                request.user.phonenumber) if request.user.phonenumber else None

            return JsonResponse({
                'status': 'success',
                'email': user_email,
                'phonenumber': user_phonenumber,
                'role': request.user.role
            })
        except Exception as e:
            logger.error(f"Error fetching user profile: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_phonenumber = data.get('phonenumber')

            if not user_phonenumber:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Phone number is required.'
                }, status=400)

            request.user.phonenumber = user_phonenumber
            request.user.save()

            return JsonResponse({
                'status': 'success',
                'message': 'Phone number updated successfully.'
            })
        except Exception as e:
            logger.error(f"Error updating phone number: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method.'
    }, status=405)


@login_required(login_url='login_user')
def delete_account(request):
    if request.method == 'POST':
        try:
            user = request.user
            user.delete()
            logout(request)

            return JsonResponse({
                'status': 'success',
                'message': 'Account deleted successfully.'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method.'
    }, status=405)


@api_view(['GET'])
def get_csrf_token(request):
    token = get_token(request)
    return Response({'csrfToken': token})


def adminlogin(request):
    return redirect('admin:index')


# Product List View
def product_list(request):
    return render(request, 'product_list.html')


@api_view(['GET'])
def get_products(request):
    try:
        category = request.GET.get('category')
        search = request.GET.get('search')

        products = Product.objects.filter(is_active=True)

        if category:
            products = products.filter(category__name=category)

        if search:
            products = products.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        products_data = [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': str(p.price),
            'stock_quantity': p.stock_quantity,
            'image_url': p.image_display_url or p.image_url,
            'category': p.category.name if p.category else None,
            'seller_email': p.seller.email,
            'in_stock': p.in_stock
        } for p in products]

        return Response({'products': products_data})
    except Exception as e:
        logger.error(f"Error fetching products: {str(e)}")
        return Response({'error': str(e)}, status=500)


# Product Detail View
def product_detail(request, product_id):
    return render(request, 'product_detail.html', {'product_id': product_id})


@api_view(['GET'])
def get_product_detail(request, product_id):
    try:
        product = get_object_or_404(Product, id=product_id, is_active=True)

        is_in_wishlist = False
        if request.user.is_authenticated:
            is_in_wishlist = Wishlist.objects.filter(
                user=request.user, product=product
            ).exists()

        product_data = {
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'price': str(product.price),
            'stock_quantity': product.stock_quantity,
            'image_url': product.image_display_url or product.image_url,
            'category': product.category.name if product.category else None,
            'seller_email': product.seller.email,
            'in_stock': product.in_stock,
            'is_in_wishlist': is_in_wishlist
        }

        return Response({'product': product_data})
    except Exception as e:
        logger.error(f"Error fetching product detail: {str(e)}")
        return Response({'error': str(e)}, status=500)


# Cart Views
@login_required(login_url='login_user')
def view_cart(request):
    return render(request, 'cart.html')


@login_required(login_url='login_user')
@api_view(['GET'])
def get_cart(request):
    try:
        cart, created = Cart.objects.get_or_create(user=request.user)

        cart_items = []
        for item in cart.items.select_related('product', 'product__seller'):
            cart_items.append({
                'id': item.id,
                'product_id': item.product.id,
                'product_name': item.product.name,
                'product_price': str(item.product.price),
                'product_image': item.product.image_display_url or item.product.image_url,
                'seller_email': item.product.seller.email,
                'quantity': item.quantity,
                'subtotal': str(item.subtotal),
                'in_stock': item.product.in_stock,
                'stock_quantity': item.product.stock_quantity
            })

        return Response({
            'cart_items': cart_items,
            'total_price': str(cart.total_price),
            'total_items': cart.total_items
        })
    except Exception as e:
        logger.error(f"Error fetching cart: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def add_to_cart(request):
    try:
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))

        product = get_object_or_404(Product, id=product_id, is_active=True)

        if quantity > product.stock_quantity:
            return Response({
                'error': 'Requested quantity exceeds available stock'
            }, status=400)

        cart, created = Cart.objects.get_or_create(user=request.user)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}
        )

        if not created:
            new_quantity = cart_item.quantity + quantity
            if new_quantity > product.stock_quantity:
                return Response({
                    'error': 'Total quantity exceeds available stock'
                }, status=400)
            cart_item.quantity = new_quantity
            cart_item.save()

        return Response({
            'message': 'Product added to cart',
            'cart_total': str(cart.total_price)
        })
    except Exception as e:
        logger.error(f"Error adding to cart: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def update_cart_item(request, item_id):
    try:
        quantity = int(request.data.get('quantity', 1))

        cart_item = get_object_or_404(
            CartItem,
            id=item_id,
            cart__user=request.user
        )

        if quantity <= 0:
            cart_item.delete()
            return Response({'message': 'Item removed from cart'})

        if quantity > cart_item.product.stock_quantity:
            return Response({
                'error': 'Requested quantity exceeds available stock'
            }, status=400)

        cart_item.quantity = quantity
        cart_item.save()

        return Response({
            'message': 'Cart updated',
            'subtotal': str(cart_item.subtotal),
            'cart_total': str(cart_item.cart.total_price)
        })
    except Exception as e:
        logger.error(f"Error updating cart: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['DELETE'])
def remove_from_cart(request, item_id):
    try:
        cart_item = get_object_or_404(
            CartItem,
            id=item_id,
            cart__user=request.user
        )
        cart_item.delete()

        return Response({'message': 'Item removed from cart'})
    except Exception as e:
        logger.error(f"Error removing from cart: {str(e)}")
        return Response({'error': str(e)}, status=500)


# Wishlist Views
@login_required(login_url='login_user')
def view_wishlist(request):
    return render(request, 'wishlist.html')


@login_required(login_url='login_user')
@api_view(['GET'])
def get_wishlist(request):
    try:
        wishlist_items = Wishlist.objects.filter(
            user=request.user
        ).select_related('product', 'product__seller', 'product__category')

        wishlist_data = [{
            'id': item.id,
            'product_id': item.product.id,
            'product_name': item.product.name,
            'product_description': item.product.description,
            'product_price': str(item.product.price),
            'product_image': item.product.image_display_url or item.product.image_url,
            'seller_email': item.product.seller.email,
            'category': item.product.category.name if item.product.category else None,
            'in_stock': item.product.in_stock,
            'stock_quantity': item.product.stock_quantity,
            'added_at': item.added_at.strftime('%Y-%m-%d %H:%M:%S')
        } for item in wishlist_items]

        return Response({
            'wishlist_items': wishlist_data,
            'total_items': len(wishlist_data)
        })
    except Exception as e:
        logger.error(f"Error fetching wishlist: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def toggle_wishlist(request):
    try:
        product_id = request.data.get('product_id')

        product = get_object_or_404(Product, id=product_id)

        wishlist_item = Wishlist.objects.filter(
            user=request.user,
            product=product
        ).first()

        if wishlist_item:
            wishlist_item.delete()
            return Response({
                'message': 'Removed from wishlist',
                'in_wishlist': False
            })
        else:
            Wishlist.objects.create(user=request.user, product=product)
            return Response({
                'message': 'Added to wishlist',
                'in_wishlist': True
            })
    except Exception as e:
        logger.error(f"Error toggling wishlist: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['DELETE'])
def remove_from_wishlist(request, wishlist_id):
    try:
        wishlist_item = get_object_or_404(
            Wishlist,
            id=wishlist_id,
            user=request.user
        )
        wishlist_item.delete()

        return Response({'message': 'Removed from wishlist'})
    except Exception as e:
        logger.error(f"Error removing from wishlist: {str(e)}")
        return Response({'error': str(e)}, status=500)


# Order Views
@login_required(login_url='login_user')
def view_orders(request):
    return render(request, 'orders.html')


@login_required(login_url='login_user')
@api_view(['GET'])
def get_orders(request):
    try:
        orders = Order.objects.filter(
            buyer=request.user
        ).prefetch_related('items__product')

        orders_data = []
        for order in orders:
            order_items = [{
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': str(item.price),
                'subtotal': str(item.subtotal),
                'seller_email': item.seller.email
            } for item in order.items.all()]

            orders_data.append({
                'id': order.id,
                'order_number': order.order_number,
                'total_amount': str(order.total_amount),
                'status': order.status,
                'status_display': order.get_status_display(),
                'items_count': order.items.count(),
                'items': order_items,
                'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': order.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            })

        return Response({
            'orders': orders_data,
            'total_orders': len(orders_data)
        })
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
def view_order_detail(request, order_id):
    return render(request, 'order_detail.html', {'order_id': order_id})



@login_required(login_url='login_user')
@api_view(['GET'])
def get_order_detail(request, order_id):
    """Enhanced order detail with payment method information"""
    try:
        order = get_object_or_404(
            Order,
            id=order_id,
            buyer=request.user
        )

        # Get order items with payment method details
        order_items = []
        for item in order.items.select_related('product', 'seller'):
            order_items.append({
                'id': item.id,
                'product_id': item.product.id,
                'product_name': item.product.name,
                'product_image': item.product.image_display_url or item.product.image_url,
                'quantity': item.quantity,
                'price': str(item.price),
                'subtotal': str(item.subtotal),
                'seller_email': item.seller.email,
                'payment_method': item.payment_method,
                'payment_method_display': item.get_payment_method_display(),
                'payment_status': item.payment_status,
                'payment_status_display': item.get_payment_status_display(),
                'payment_options': item.payment_options,  
                'can_pay_online': item.can_pay_online    
            })

        # Get seller payment summaries (no longer using SellerPayment model)
        # Group items by seller and payment method
        seller_summaries = {}
        for item in order.items.all():
            seller_key = item.seller.email
            if seller_key not in seller_summaries:
                seller_summaries[seller_key] = {
                    'seller_email': seller_key,
                    'items': [],
                    'total_amount': Decimal('0.00'),
                    'online_amount': Decimal('0.00'),
                    'cash_amount': Decimal('0.00'),
                    'online_paid': False,
                    'has_online_items': False
                }
            
            seller_summaries[seller_key]['items'].append({
                'name': item.product.name,
                'quantity': item.quantity,
                'subtotal': str(item.subtotal),
                'payment_method': item.payment_method,
                'payment_status': item.payment_status
            })
            
            seller_summaries[seller_key]['total_amount'] += item.subtotal
            
            if item.payment_method == 'online':
                seller_summaries[seller_key]['online_amount'] += item.subtotal
                seller_summaries[seller_key]['has_online_items'] = True
                if item.payment_status == 'paid':
                    seller_summaries[seller_key]['online_paid'] = True
            else:
                seller_summaries[seller_key]['cash_amount'] += item.subtotal

        # Convert to list
        seller_payments = []
        for summary in seller_summaries.values():
            # Determine overall payment status for this seller
            if summary['has_online_items']:
                if summary['online_paid']:
                    status = 'paid'
                    status_display = 'Paid Online'
                else:
                    status = 'pending'
                    status_display = 'Pending Payment'
            else:
                status = 'pending'
                status_display = 'Cash on Delivery'
            
            seller_payments.append({
                'seller_email': summary['seller_email'],
                'total_amount': str(summary['total_amount']),
                'online_amount': str(summary['online_amount']),
                'cash_amount': str(summary['cash_amount']),
                'status': status,
                'status_display': status_display,
                'items': summary['items']
            })

        # Check if there are unpaid online items
        has_unpaid_online = order.items.filter(
            payment_options__contains='online',  # ✅ Item supports online payment
            payment_status='pending'  # ✅ Payment is still pending
        ).exists()

        order_data = {
            'id': order.id,
            'order_number': order.order_number,
            'total_amount': str(order.total_amount),
            'status': order.status,
            'status_display': order.get_status_display(),
            'payment_method': order.payment_method,
            'payment_method_display': order.get_payment_method_display(),
            'online_payment_status': order.online_payment_status,
            'online_payment_status_display': order.get_online_payment_status_display(),
            'fair_cashier_request_id': str(order.fair_cashier_request_id) if order.fair_cashier_request_id else None,
            'items': order_items,
            'seller_payments': seller_payments,
            'has_unpaid_online': has_unpaid_online,
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': order.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            
        }

        return Response({'order': order_data})
    except Exception as e:
        logger.error(f"Error fetching order detail: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def retry_online_payment(request, order_id):
    """
    Retry online payment for an order with failed/pending payment
    
    Creates a new Fair Cashier payment request for unpaid online items
    """
    try:
        order = get_object_or_404(
            Order,
            id=order_id,
            buyer=request.user
        )
        
        # Get unpaid online items
        unpaid_items = order.items.filter(
            payment_method='online',
            payment_status='pending'
        ).select_related('product', 'seller')
        
        if not unpaid_items.exists():
            return Response({
                'error': 'No unpaid online items in this order'
            }, status=400)
        
        # Group by seller
        seller_amounts = {}
        for item in unpaid_items:
            seller_email = item.seller.email
            if seller_email not in seller_amounts:
                seller_amounts[seller_email] = {
                    'amount': Decimal('0.00'),
                    'description': []
                }
            seller_amounts[seller_email]['amount'] += item.subtotal
            seller_amounts[seller_email]['description'].append(
                f"{item.product.name} (×{item.quantity})"
            )
        
        # Create payment request items
        payment_items = []
        for seller_email, data in seller_amounts.items():
            payment_items.append({
                'seller_email': seller_email,
                'amount': str(data['amount']),
                'description': ', '.join(data['description'])
            })
        
        # Call Fair Cashier API
        import requests
        from django.conf import settings
        
        try:
            response = requests.post(
                f"{settings.FAIR_CASHIER_API_URL}/api/payment-request/create/",
                json={
                    'api_key': settings.FAIR_CASHIER_API_KEY,
                    'buyer_email': request.user.email,
                    'items': payment_items,
                    'metadata': {
                        'order_id': order.id,
                        'order_number': order.order_number,
                        'retry': True
                    }
                },
                headers={'Content-Type': 'application/json'},
                timeout=15
            )
            
            if response.status_code in [200, 201]:
                payment_data = response.json()
                
                # Update order with new payment request
                order.fair_cashier_request_id = payment_data['request_id']
                order.online_payment_status = 'pending'
                order.save()
                
                # Store payment info in session - INCLUDING online_item_ids
                request.session['pending_payment'] = {
                    'request_id': str(payment_data['request_id']),
                    'amount': str(sum(Decimal(item['amount']) for item in payment_items)),
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'online_item_ids': list(unpaid_items.values_list('id', flat=True))  # ✅ ADD THIS
                }
                
                logger.info(f"✅ Payment retry created for order {order.order_number}")
                
                return Response({
                    'success': True,
                    'payment_request_id': payment_data['request_id'],
                    'order_id': order.id,
                    'order_number': order.order_number,
                    
                })
            else:
                logger.error(f"Failed to create payment request: {response.text}")
                return Response({
                    'error': 'Failed to create payment request',
                    'details': response.text
                }, status=500)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to payment gateway: {str(e)}")
            return Response({
                'error': 'Failed to connect to payment gateway',
                'message': str(e)
            }, status=503)
            
    except Exception as e:
        logger.error(f"Error retrying payment: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def retry_selected_items_payment(request, order_id):
    """
    Create payment request for selected order items
    
    Request body: {
        "item_ids": [1, 2, 3]  // IDs of items to pay for
    }
    """
    try:
        order = get_object_or_404(
            Order,
            id=order_id,
            buyer=request.user
        )
        
        item_ids = request.data.get('item_ids', [])
        
        if not item_ids:
            return Response({
                'error': 'No items selected'
            }, status=400)
        
        # Get selected items that can be paid online and are pending
        selected_items = order.items.filter(
            id__in=item_ids,
            payment_options__contains='online',
            payment_status='pending'
        ).select_related('product', 'seller')
        
        if not selected_items.exists():
            return Response({
                'error': 'No valid items selected for online payment'
            }, status=400)
        
        # Group by seller
        seller_amounts = {}
        for item in selected_items:
            seller_email = item.seller.email
            if seller_email not in seller_amounts:
                seller_amounts[seller_email] = {
                    'amount': Decimal('0.00'),
                    'description': []
                }
            seller_amounts[seller_email]['amount'] += item.subtotal
            seller_amounts[seller_email]['description'].append(
                f"{item.product.name} (×{item.quantity})"
            )
        
        # Create payment request items
        payment_items = []
        for seller_email, data in seller_amounts.items():
            payment_items.append({
                'seller_email': seller_email,
                'amount': str(data['amount']),
                'description': ', '.join(data['description'])
            })
        
        # Call Fair Cashier API
        import requests
        from django.conf import settings
        
        try:
            response = requests.post(
                f"{settings.FAIR_CASHIER_API_URL}/api/payment-request/create/",
                json={
                    'api_key': settings.FAIR_CASHIER_API_KEY,
                    'buyer_email': request.user.email,
                    'items': payment_items,
                    'metadata': {
                        'order_id': order.id,
                        'order_number': order.order_number,
                        'partial_payment': True
                    }
                },
                headers={'Content-Type': 'application/json'},
                timeout=15
            )
            
            if response.status_code in [200, 201]:
                payment_data = response.json()
                
                # Update order with new payment request
                order.fair_cashier_request_id = payment_data['request_id']
                order.online_payment_status = 'pending'
                order.save()
                
                # Store payment info in session
                request.session['pending_payment'] = {
                    'request_id': str(payment_data['request_id']),
                    'amount': str(sum(Decimal(item['amount']) for item in payment_items)),
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'online_item_ids': list(selected_items.values_list('id', flat=True))
                }
                
                logger.info(f"✅ Selective payment created for order {order.order_number}, items: {item_ids}")
                
                return Response({
                    'success': True,
                    'payment_request_id': payment_data['request_id'],
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'total_amount': str(sum(Decimal(item['amount']) for item in payment_items))
                })
            else:
                logger.error(f"Failed to create payment request: {response.text}")
                return Response({
                    'error': 'Failed to create payment request',
                    'details': response.text
                }, status=500)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error connecting to payment gateway: {str(e)}")
            return Response({
                'error': 'Failed to connect to payment gateway',
                'message': str(e)
            }, status=503)
            
    except Exception as e:
        logger.error(f"Error creating selective payment: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)

@login_required(login_url='login_user')
@api_view(['POST'])
def process_payment_selection(request):
    """
    Process payment method selections and create payment request if needed
    """
    try:
        data = request.data
        selections = data.get('selections', {})
        
        # Get seller payment capabilities from session
        seller_payment_capabilities = request.session.get('seller_payment_capabilities', {})
        
        # Get cart
        cart = get_object_or_404(Cart, user=request.user)
        
        if not cart.items.exists():
            return Response({'error': 'Cart is empty'}, status=400)
        
        with transaction.atomic():
            # Create order first
            order = Order.objects.create(
                buyer=request.user,
                total_amount=cart.total_price,
                status='pending'
            )
            
            # Group items by seller and payment method
            online_items = []
            cash_items = []
            
            for item in cart.items.all():
                seller_email = item.product.seller.email
                payment_method = selections.get(seller_email, 'cash')
                
                # Get payment options for this seller
                seller_capabilities = seller_payment_capabilities.get(seller_email, {})
                payment_options = ['cash']  # Cash always available
                if seller_capabilities.get('online', False):
                    payment_options.append('online')
                
                # Create order item
                order_item = OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    seller=item.product.seller,
                    quantity=item.quantity,
                    price=item.product.price,
                    subtotal=item.subtotal,
                    payment_method=payment_method,
                    payment_status='pending',
                    payment_options=payment_options 
                )
                
                # Update stock
                product = item.product
                product.stock_quantity -= item.quantity
                product.save()
                
                # Group for payment request
                if payment_method == 'online':
                    online_items.append({
                        'seller_email': seller_email,
                        'product': item.product,
                        'order_item': order_item
                    })
                else:
                    cash_items.append(order_item)
            
            # Clear cart
            cart.items.all().delete()
            
            # Clear seller payment capabilities from session
            request.session.pop('seller_payment_capabilities', None)
            
            # Determine overall payment method
            if online_items and cash_items:
                order.payment_method = 'mixed'
            elif online_items:
                order.payment_method = 'online'
            else:
                order.payment_method = 'cash'
                
            
            order.save()
            
            # If online payment required, create Fair Cashier payment request
            if online_items:
                
                # Group by seller
                seller_amounts = {}
                for item_data in online_items:
                    seller_email = item_data['seller_email']
                    if seller_email not in seller_amounts:
                        seller_amounts[seller_email] = {
                            'amount': Decimal('0.00'),
                            'description': []
                        }
                    seller_amounts[seller_email]['amount'] += item_data['order_item'].subtotal
                    seller_amounts[seller_email]['description'].append(
                        f"{item_data['product'].name} (×{item_data['order_item'].quantity})"
                    )
                
                # Create payment request items
                payment_items = []
                for seller_email, data in seller_amounts.items():
                    payment_items.append({
                        'seller_email': seller_email,
                        'amount': str(data['amount']),
                        'description': ', '.join(data['description'])
                    })
                
                # Call Fair Cashier API to create payment request
                import requests
                from django.conf import settings
                
                try:
                    response = requests.post(
                        f"{settings.FAIR_CASHIER_API_URL}/api/payment-request/create/",
                        json={
                            'api_key': settings.FAIR_CASHIER_API_KEY,
                            'buyer_email': request.user.email,
                            'items': payment_items,
                            'metadata': {
                                'order_id': order.id,
                                'order_number': order.order_number
                            }
                        },
                        headers={'Content-Type': 'application/json'},
                        timeout=15
                    )
                    
                    if response.status_code in [200, 201]:
                        payment_data = response.json()
                        
                        # Save payment request ID to order
                        order.fair_cashier_request_id = payment_data['request_id']
                        order.online_payment_status = 'pending'
                        order.save()
                        
                        # Store payment info in session for iframe proxy authorization
                        request.session['pending_payment'] = {
                            'request_id': str(payment_data['request_id']),
                            'amount': str(sum(Decimal(item['amount']) for item in payment_items)),
                            'order_id': order.id,
                            'order_number': order.order_number,
                            'online_item_ids': [item_data['order_item'].id for item_data in online_items]
                        }
                        
                        return Response({
                            'success': True,
                            'online_payment_required': True,
                            'payment_request_id': payment_data['request_id'],
                            'order_id': order.id,
                            'order_number': order.order_number
                        })
                    else:
                        # Payment request creation failed
                        logger.error(f"Failed to create payment request: {response.text}")
                        order.online_payment_status = 'failed'
                        order.save()
                        
                        return Response({
                            'error': 'Failed to create payment request',
                            'details': response.text
                        }, status=500)
                        
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error connecting to payment gateway: {str(e)}")
                    order.online_payment_status = 'failed'
                    order.save()
                    
                    return Response({
                        'error': 'Failed to connect to payment gateway',
                        'message': str(e)
                    }, status=503)
            
            # No online payment needed - all cash
            return Response({
                'success': True,
                'online_payment_required': False,
                'order_id': order.id,
                'order_number': order.order_number
            })
            
    except Exception as e:
        logger.error(f"Error processing payment selection: {str(e)}", exc_info=True)
        return Response({'error': str(e)}, status=500)

@login_required(login_url='login_user')
def payment_selection_page(request):
    """
    Display payment method selection page
    Shows which sellers accept online payment vs cash only
    """
    try:
        cart = get_object_or_404(Cart, user=request.user)
        
        if not cart.items.exists():
            messages.warning(request, 'Your cart is empty')
            return redirect('product_list')
        
        # Group items by seller
        seller_items = {}
        for item in cart.items.select_related('product__seller'):
            seller_email = item.product.seller.email
            
            if seller_email not in seller_items:
                seller_items[seller_email] = {
                    'items': [],
                    'total': Decimal('0.00'),
                    'payment_options': None
                }
            
            seller_items[seller_email]['items'].append(item)
            seller_items[seller_email]['total'] += item.subtotal
        
        # Check payment options for each seller
        import requests
        from django.conf import settings
        
        # Store seller payment capabilities for later use
        seller_payment_capabilities = {}
        
        try:
            seller_emails = list(seller_items.keys())
            
            response = requests.post(
                f"{settings.FAIR_CASHIER_API_URL}/api/check-sellers/",
                json={
                    'api_key': settings.FAIR_CASHIER_API_KEY,
                    'seller_emails': seller_emails
                },
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                results = response.json().get('results', {})
                
                for seller_email in seller_items:
                    seller_data = results.get(seller_email, {})
                    supports_online = seller_data.get('registered', False) and seller_data.get('has_wallet', False)
                    
                    seller_items[seller_email]['payment_options'] = {
                        'online': supports_online,
                        'cash': True
                    }
                    
                    # Store for session
                    seller_payment_capabilities[seller_email] = {
                        'online': supports_online,
                        'cash': True
                    }
            else:
                # If check fails, default to cash only
                logger.warning(f"Seller check failed: {response.status_code}")
                for seller_email in seller_items:
                    seller_items[seller_email]['payment_options'] = {
                        'online': False,
                        'cash': True
                    }
                    seller_payment_capabilities[seller_email] = {
                        'online': False,
                        'cash': True
                    }
        except Exception as e:
            logger.error(f"Error checking sellers: {str(e)}")
            # Default to cash only on error
            for seller_email in seller_items:
                seller_items[seller_email]['payment_options'] = {
                    'online': False,
                    'cash': True
                }
                seller_payment_capabilities[seller_email] = {
                    'online': False,
                    'cash': True
                }
        
        # Store seller payment capabilities in session for use during order creation
        request.session['seller_payment_capabilities'] = seller_payment_capabilities
        
        context = {
            'grouped_items': seller_items,
            'total_amount': cart.total_price
        }
        
        return render(request, 'payment_selection.html', context)
        
    except Exception as e:
        logger.error(f"Error loading payment selection: {str(e)}")
        messages.error(request, 'Failed to load payment options')
        return redirect('view_cart')

@login_required(login_url='login_user')
def checkout(request):
    
    return redirect('payment_selection_page')


@login_required(login_url='login_user')
@api_view(['POST'])
def process_checkout(request):
    try:
        with transaction.atomic():
            cart = get_object_or_404(Cart, user=request.user)

            if not cart.items.exists():
                return Response({
                    'error': 'Cart is empty'
                }, status=400)

            # Check stock availability
            for item in cart.items.all():
                if item.quantity > item.product.stock_quantity:
                    return Response({
                        'error': f'Insufficient stock for {item.product.name}'
                    }, status=400)

            # Create order
            order = Order.objects.create(
                buyer=request.user,
                total_amount=cart.total_price,
                status='pending'
            )

            # Group items by seller for payment distribution
            seller_totals = {}

            # Create order items
            for item in cart.items.all():
                order_item = OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    seller=item.product.seller,
                    quantity=item.quantity,
                    price=item.product.price,
                    subtotal=item.subtotal
                )

                # Update stock
                product = item.product
                product.stock_quantity -= item.quantity
                product.save()

                # Track seller totals
                seller_id = item.product.seller.id
                if seller_id not in seller_totals:
                    seller_totals[seller_id] = {
                        'seller': item.product.seller,
                        'amount': Decimal('0.00')
                    }
                seller_totals[seller_id]['amount'] += item.subtotal

            # Create seller payment records
            for seller_data in seller_totals.values():
                SellerPayment.objects.create(
                    order=order,
                    seller=seller_data['seller'],
                    amount=seller_data['amount'],
                    status='completed'
                )

            # Clear cart
            cart.items.all().delete()

            return Response({
                'message': 'Order placed successfully',
                'order_number': order.order_number,
                'order_id': order.id,
                'total_amount': str(order.total_amount)
            })
    except Exception as e:
        logger.error(f"Error processing checkout: {str(e)}")
        return Response({'error': str(e)}, status=500)


# Seller Views
@login_required(login_url='login_user')
def seller_dashboard(request):
    if request.user.role != 'seller':
        return redirect('home')
    return render(request, 'seller_dashboard.html')


@login_required(login_url='login_user')
@api_view(['GET'])
def get_seller_sales(request):
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        # Get all payments for this seller
        payments = SellerPayment.objects.filter(
            seller=request.user
        ).select_related('order', 'order__buyer')

        sales_data = []
        total_revenue = Decimal('0.00')

        for payment in payments:
            sales_data.append({
                'order_number': payment.order.order_number,
                'buyer_email': payment.order.buyer.email,
                'amount': str(payment.amount),
                'status': payment.status,
                'status_display': payment.get_status_display(),
                'created_at': payment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })

            if payment.status == 'completed':
                total_revenue += payment.amount

        # Get sales statistics
        stats = {
            'total_sales': payments.count(),
            'total_revenue': str(total_revenue),
            'pending_payments': payments.filter(status='pending').count(),
            'completed_payments': payments.filter(status='completed').count()
        }

        return Response({
            'sales': sales_data,
            'statistics': stats
        })
    except Exception as e:
        logger.error(f"Error fetching seller sales: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['GET'])
def get_seller_products(request):
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        products = Product.objects.filter(seller=request.user)

        products_data = [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'price': str(p.price),
            'stock_quantity': p.stock_quantity,
            'image_url': p.image_display_url or p.image_url,
            'category': p.category.name if p.category else None,
            'is_active': p.is_active,
            'in_stock': p.in_stock,
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for p in products]

        return Response({
            'products': products_data,
            'total_products': len(products_data)
        })
    except Exception as e:
        logger.error(f"Error fetching seller products: {str(e)}")
        return Response({'error': str(e)}, status=500)

# Seller Product Management Views


@login_required(login_url='login_user')
def seller_products(request):
    """Display seller's product management page"""
    if request.user.role != 'seller':
        return redirect('home')
    return render(request, 'seller_products.html')


@login_required(login_url='login_user')
def seller_add_product(request):
    """Display add product page"""
    if request.user.role != 'seller':
        return redirect('home')
    return render(request, 'seller_add_product.html')


@login_required(login_url='login_user')
def seller_edit_product(request, product_id):
    """Display edit product page"""
    if request.user.role != 'seller':
        return redirect('home')
    return render(request, 'seller_edit_product.html', {'product_id': product_id})


@login_required(login_url='login_user')
@api_view(['GET'])
def get_categories(request):
    """Get all product categories"""
    try:
        categories = Category.objects.all()
        categories_data = [{
            'id': cat.id,
            'name': cat.name,
            'description': cat.description
        } for cat in categories]

        return Response({'categories': categories_data})
    except Exception as e:
        logger.error(f"Error fetching categories: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def create_product(request):
    """Create a new product"""
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        name = request.data.get('name')
        description = request.data.get('description')
        price = request.data.get('price')
        stock_quantity = request.data.get('stock_quantity')
        category_id = request.data.get('category_id')
        image = request.FILES.get('image')
        image_url = request.data.get('image_url', '')

        # Validation
        if not all([name, description, price, stock_quantity]):
            return Response({
                'error': 'Name, description, price, and stock quantity are required'
            }, status=400)

        # Validate image if provided
        if image:
            # Check file size (5MB max)
            if image.size > 5 * 1024 * 1024:
                return Response({
                    'error': 'Image file size must be less than 5MB'
                }, status=400)

            # Check file extension
            ext = image.name.split('.')[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                return Response({
                    'error': 'Invalid image format. Allowed: jpg, jpeg, png, gif, webp'
                }, status=400)

        # Get category
        category = None
        if category_id:
            category = get_object_or_404(Category, id=category_id)

        # Create product
        product = Product.objects.create(
            seller=request.user,
            name=name,
            description=description,
            price=Decimal(price),
            stock_quantity=int(stock_quantity),
            category=category,
            image=image if image else None,
            image_url=image_url if not image else '',
            is_active=True
        )

        logger.info(
            f"Product created: {product.id} by seller {request.user.email}")

        return Response({
            'message': 'Product created successfully',
            'product': {
                'id': product.id,
                'name': product.name,
                'price': str(product.price),
                'image_url': product.image_display_url
            }
        }, status=201)

    except Exception as e:
        logger.error(f"Error creating product: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['GET'])
def get_seller_product_detail(request, product_id):
    """Get detailed information about a seller's product"""
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        product = get_object_or_404(
            Product,
            id=product_id,
            seller=request.user
        )

        product_data = {
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'price': str(product.price),
            'stock_quantity': product.stock_quantity,
            'category_id': product.category.id if product.category else None,
            'category_name': product.category.name if product.category else None,
            'image_url': product.image_display_url,
            'has_uploaded_image': bool(product.image),
            'external_image_url': product.image_url,
            'is_active': product.is_active,
            'in_stock': product.in_stock,
            'created_at': product.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': product.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

        return Response({'product': product_data})

    except Exception as e:
        logger.error(f"Error fetching product detail: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['PUT'])
def update_product(request, product_id):
    """Update an existing product"""
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        product = get_object_or_404(
            Product,
            id=product_id,
            seller=request.user
        )

        # Update fields
        if 'name' in request.data:
            product.name = request.data['name']
        if 'description' in request.data:
            product.description = request.data['description']
        if 'price' in request.data:
            product.price = Decimal(request.data['price'])
        if 'stock_quantity' in request.data:
            product.stock_quantity = int(request.data['stock_quantity'])
        if 'category_id' in request.data:
            if request.data['category_id']:
                product.category = get_object_or_404(
                    Category, id=request.data['category_id'])
            else:
                product.category = None
        if 'is_active' in request.data:
            product.is_active = request.data['is_active'] in [
                True, 'true', '1']

        # Handle image upload
        if 'image' in request.FILES:
            image = request.FILES['image']

            # Validate image
            if image.size > 5 * 1024 * 1024:
                return Response({
                    'error': 'Image file size must be less than 5MB'
                }, status=400)

            ext = image.name.split('.')[-1].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                return Response({
                    'error': 'Invalid image format'
                }, status=400)

            # Delete old image if exists
            if product.image:
                if os.path.isfile(product.image.path):
                    os.remove(product.image.path)

            product.image = image
            product.image_url = ''  # Clear external URL when uploading

        # Handle external image URL
        elif 'image_url' in request.data:
            product.image_url = request.data['image_url']

        product.save()

        logger.info(
            f"Product updated: {product.id} by seller {request.user.email}")

        return Response({
            'message': 'Product updated successfully',
            'product': {
                'id': product.id,
                'name': product.name,
                'price': str(product.price),
                'image_url': product.image_display_url
            }
        })

    except Exception as e:
        logger.error(f"Error updating product: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['DELETE'])
def delete_product(request, product_id):
    """Delete a product"""
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        product = get_object_or_404(
            Product,
            id=product_id,
            seller=request.user
        )

        # Delete image file if exists
        if product.image:
            if os.path.isfile(product.image.path):
                os.remove(product.image.path)

        product_name = product.name
        product.delete()

        logger.info(
            f"Product deleted: {product_id} ({product_name}) by seller {request.user.email}")

        return Response({'message': 'Product deleted successfully'})

    except Exception as e:
        logger.error(f"Error deleting product: {str(e)}")
        return Response({'error': str(e)}, status=500)


# Seller Cash-out Views

@login_required(login_url='login_user')
def seller_cashout(request):
    """Display seller's cash-out page"""
    if request.user.role != 'seller':
        return redirect('home')
    return render(request, 'seller_cashout.html')


@login_required(login_url='login_user')
@api_view(['GET'])
def get_seller_balance(request):
    """Get seller's available balance"""
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        available_balance = request.user.available_balance

        # Get total earned
        total_earned = SellerPayment.objects.filter(
            seller=request.user,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        # Get total withdrawn
        total_withdrawn = CashOut.objects.filter(
            seller=request.user,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        # Get pending cashouts
        pending_cashouts = CashOut.objects.filter(
            seller=request.user,
            status__in=['pending', 'processing']
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        return Response({
            'available_balance': str(available_balance),
            'total_earned': str(total_earned),
            'total_withdrawn': str(total_withdrawn),
            'pending_cashouts': str(pending_cashouts)
        })

    except Exception as e:
        logger.error(f"Error fetching seller balance: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def request_cashout(request):
    """Request a cash-out"""
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        amount = Decimal(request.data.get('amount', '0'))
        payment_method = request.data.get('payment_method', 'bank_transfer')
        payment_details = request.data.get('payment_details', {})

        # Validation
        if amount <= 0:
            return Response({'error': 'Invalid amount'}, status=400)

        # Check available balance
        available_balance = request.user.available_balance
        if amount > available_balance:
            return Response({
                'error': f'Insufficient balance. Available: ${available_balance}'
            }, status=400)

        # Minimum cashout amount
        if amount < Decimal('10.00'):
            return Response({
                'error': 'Minimum cash-out amount is $10.00'
            }, status=400)

        # Create cashout request
        cashout = CashOut.objects.create(
            seller=request.user,
            amount=amount,
            payment_method=payment_method,
            payment_details=payment_details,
            status='pending'
        )

        logger.info(
            f"Cashout requested: {cashout.cashout_number} by {request.user.email} for ${amount}")

        return Response({
            'message': 'Cash-out request submitted successfully',
            'cashout': {
                'cashout_number': cashout.cashout_number,
                'amount': str(cashout.amount),
                'processing_fee': str(cashout.processing_fee),
                'net_amount': str(cashout.net_amount),
                'status': cashout.status
            }
        }, status=201)

    except Exception as e:
        logger.error(f"Error requesting cashout: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['GET'])
def get_cashout_history(request):
    """Get seller's cash-out history"""
    try:
        if request.user.role != 'seller':
            return Response({'error': 'Access denied'}, status=403)

        cashouts = CashOut.objects.filter(
            seller=request.user
        ).order_by('-created_at')

        cashouts_data = [{
            'id': co.id,
            'cashout_number': co.cashout_number,
            'amount': str(co.amount),
            'processing_fee': str(co.processing_fee),
            'net_amount': str(co.net_amount),
            'payment_method': co.payment_method,
            'status': co.status,
            'status_display': co.get_status_display(),
            'created_at': co.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'completed_at': co.completed_at.strftime('%Y-%m-%d %H:%M:%S') if co.completed_at else None
        } for co in cashouts]

        return Response({'cashouts': cashouts_data})

    except Exception as e:
        logger.error(f"Error fetching cashout history: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def update_user_role(request):
    """Update user's role (switch between buyer and seller)"""
    try:
        new_role = request.data.get('role')

        if new_role not in ['buyer', 'seller']:
            return Response({
                'error': 'Invalid role. Must be buyer or seller'
            }, status=400)

        # Prevent admin/superadmin from switching
        if request.user.role in ['admin', 'superadmin']:
            return Response({
                'error': 'Administrators cannot switch roles'
            }, status=403)

        old_role = request.user.role
        request.user.role = new_role
        request.user.save()

        logger.info(
            f"User {request.user.email} switched role from {old_role} to {new_role}")

        return Response({
            'message': f'Role updated to {new_role}',
            'role': new_role
        })

    except Exception as e:
        logger.error(f"Error updating role: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['GET'])
def get_user_details(request):
    """Get complete user details including role"""
    try:
        user = request.user

        return Response({
            'id': user.id,
            'email': user.email,
            'role': user.role,
            'phonenumber': str(user.phonenumber) if user.phonenumber else None,
            'is_active': user.is_active,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        logger.error(f"Error fetching user details: {str(e)}")
        return Response({'error': str(e)}, status=500)


@login_required(login_url='login_user')
@api_view(['POST'])
def update_user_password(request):
    """Update user password"""
    try:
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not all([current_password, new_password, confirm_password]):
            return Response({
                'error': 'All password fields are required'
            }, status=400)

        if new_password != confirm_password:
            return Response({
                'error': 'New passwords do not match'
            }, status=400)

        # Verify current password
        if not request.user.check_password(current_password):
            return Response({
                'error': 'Current password is incorrect'
            }, status=400)

        # Validate new password strength (basic)
        if len(new_password) < 8:
            return Response({
                'error': 'Password must be at least 8 characters long'
            }, status=400)

        # Update password
        request.user.set_password(new_password)
        request.user.save()

        # Update session to prevent logout
        update_session_auth_hash(request, request.user)

        logger.info(f"Password updated for user {request.user.email}")

        return Response({
            'message': 'Password updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating password: {str(e)}")
        return Response({'error': str(e)}, status=500)




