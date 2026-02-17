# shopping_app/management/commands/populate_buyers.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from shopping_app.models import Users, Cart, CartItem, Wishlist, Product, Order, OrderItem, Category


class Command(BaseCommand):
    help = 'Populates the database with sample buyers and their data'

    def handle(self, *args, **kwargs):
        # Create sample buyers
        buyer_emails = [
            'buyer1@example.com',
            'buyer2@example.com',
            'buyer3@example.com',
            'buyer4@example.com',
            'buyer5@example.com'
        ]

        buyers = []
        for email in buyer_emails:
            buyer, created = Users.objects.get_or_create(
                email=email,
                defaults={
                    'role': 'buyer',
                    'is_staff': False,
                    'is_superuser': False
                }
            )
            if created:
                buyer.set_password('buyer123')
                buyer.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Created buyer: {email}'))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Buyer already exists: {email}'))
            buyers.append(buyer)

        # Create carts for buyers
        for buyer in buyers:
            cart, created = Cart.objects.get_or_create(user=buyer)
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Created cart for: {buyer.email}'))

        # Add items to carts (if products exist)
        products = Product.objects.all()[:10]  # Get first 10 products
        
        if products.exists():
            self.stdout.write(self.style.SUCCESS(
                f'\nAdding items to carts...'))
            
            for i, buyer in enumerate(buyers):
                cart = Cart.objects.get(user=buyer)
                
                # Add 2-3 random products to each cart
                for j in range(2):
                    if j < len(products):
                        product = products[(i + j) % len(products)]
                        cart_item, created = CartItem.objects.get_or_create(
                            cart=cart,
                            product=product,
                            defaults={'quantity': j + 1}
                        )
                        if created:
                            self.stdout.write(self.style.SUCCESS(
                                f'Added {product.name} to {buyer.email}\'s cart'))

        # Create wishlists
        if products.exists():
            self.stdout.write(self.style.SUCCESS(
                f'\nCreating wishlists...'))
            
            for i, buyer in enumerate(buyers):
                # Add 2-3 products to wishlist
                for j in range(2):
                    if j < len(products):
                        product = products[(i + j + 2) % len(products)]
                        wishlist, created = Wishlist.objects.get_or_create(
                            user=buyer,
                            product=product
                        )
                        if created:
                            self.stdout.write(self.style.SUCCESS(
                                f'Added {product.name} to {buyer.email}\'s wishlist'))

        # Create sample orders (if products and sellers exist)
        sellers = Users.objects.filter(role='seller')[:3]
        
        if products.exists() and sellers.exists():
            self.stdout.write(self.style.SUCCESS(
                f'\nCreating sample orders...'))
            
            for i, buyer in enumerate(buyers[:3]):  # Create orders for first 3 buyers
                seller = sellers[i % len(sellers)]
                
                # Create order
                order = Order.objects.create(
                    buyer=buyer,
                    total_amount=0,
                    status='processing',
                    payment_method='cash',
                    online_payment_status='pending',
                )
                
                # Add 2 order items
                total = 0
                for j in range(2):
                    if j < len(products):
                        product = products[(i + j) % len(products)]
                        quantity = j + 1
                        subtotal = product.price * quantity
                        total += subtotal
                        
                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            seller=seller,
                            quantity=quantity,
                            price=product.price,
                            subtotal=subtotal,
                            payment_method='cash',
                            payment_status='pending',
                            payment_options=['cash']
                        )
                
                # Update total amount
                order.total_amount = total
                order.save()
                
                self.stdout.write(self.style.SUCCESS(
                    f'Created order {order.order_number} for {buyer.email} - Total: UGX {total:,.0f}'))

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'\n' + '='*50 + '\n'
                f'SUCCESSFULLY POPULATED BUYERS DATA\n'
                f'='*50 + '\n'
                f'Buyers created: {len(buyers)}\n'
                f'Carts created: {Cart.objects.count()}\n'
                f'Cart items: {CartItem.objects.count()}\n'
                f'Wishlists: {Wishlist.objects.count()}\n'
                f'Orders created: {Order.objects.filter(buyer__in=buyers).count()}\n'
                f'\nLogin credentials:\n'
                f'Email: buyer1@example.com - buyer5@example.com\n'
                f'Password: buyer123\n'
                f'='*50
            )
        )