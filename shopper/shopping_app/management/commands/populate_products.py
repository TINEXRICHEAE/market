# shopping_app/management/commands/populate_products.py

from django.core.management.base import BaseCommand
from shopping_app.models import Users, Category, Product


class Command(BaseCommand):
    help = 'Populates the database with sample products'

    def handle(self, *args, **kwargs):
        # Create sample sellers
        sellers = []
        seller_emails = [
            'seller1@example.com',
            'seller2@example.com',
            'seller3@example.com'
        ]

        for email in seller_emails:
            seller, created = Users.objects.get_or_create(
                email=email,
                defaults={
                    'role': 'seller',
                    'is_staff': False,
                    'is_superuser': False
                }
            )
            if created:
                seller.set_password('password123')
                seller.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Created seller: {email}'))
            sellers.append(seller)

        # Create categories
        categories_data = [
            {'name': 'Electronics', 'description': 'Electronic devices and accessories'},
            {'name': 'Clothing', 'description': 'Fashion and apparel'},
            {'name': 'Home & Garden',
                'description': 'Home improvement and garden supplies'},
            {'name': 'Books', 'description': 'Books and reading materials'},
            {'name': 'Sports', 'description': 'Sports equipment and accessories'},
        ]

        categories = {}
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']}
            )
            categories[cat_data['name']] = category
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Created category: {cat_data["name"]}'))

        # Create sample products
        products_data = [
            {
                'name': 'Wireless Bluetooth Headphones',
                'description': 'High-quality wireless headphones with noise cancellation and 30-hour battery life. Perfect for music lovers and professionals.',
                'price': 79.99,
                'stock_quantity': 50,
                'category': 'Electronics',
                'image_url': 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500'
            },
            {
                'name': 'Smart Watch Pro',
                'description': 'Feature-packed smartwatch with fitness tracking, heart rate monitor, and smartphone notifications.',
                'price': 299.99,
                'stock_quantity': 30,
                'category': 'Electronics',
                'image_url': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=500'
            },
            {
                'name': 'Laptop Stand Adjustable',
                'description': 'Ergonomic aluminum laptop stand with multiple angle adjustments for comfortable working.',
                'price': 39.99,
                'stock_quantity': 100,
                'category': 'Electronics',
                'image_url': 'https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?w=500'
            },
            {
                'name': 'Cotton T-Shirt Pack',
                'description': 'Premium quality 100% cotton t-shirts in various colors. Pack of 3. Comfortable and durable.',
                'price': 29.99,
                'stock_quantity': 200,
                'category': 'Clothing',
                'image_url': 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=500'
            },
            {
                'name': 'Denim Jeans Classic',
                'description': 'Classic fit denim jeans with modern styling. Available in multiple sizes.',
                'price': 59.99,
                'stock_quantity': 75,
                'category': 'Clothing',
                'image_url': 'https://images.unsplash.com/photo-1542272604-787c3835535d?w=500'
            },
            {
                'name': 'Winter Jacket',
                'description': 'Warm and stylish winter jacket with water-resistant outer layer. Perfect for cold weather.',
                'price': 129.99,
                'stock_quantity': 40,
                'category': 'Clothing',
                'image_url': 'https://images.unsplash.com/photo-1551028719-00167b16eac5?w=500'
            },
            {
                'name': 'Indoor Plant Collection',
                'description': 'Set of 3 easy-care indoor plants including pots. Brings life to any room.',
                'price': 45.00,
                'stock_quantity': 60,
                'category': 'Home & Garden',
                'image_url': 'https://images.unsplash.com/photo-1485955900006-10f4d324d411?w=500'
            },
            {
                'name': 'LED Desk Lamp',
                'description': 'Modern LED desk lamp with adjustable brightness and color temperature. USB charging port included.',
                'price': 34.99,
                'stock_quantity': 80,
                'category': 'Home & Garden',
                'image_url': 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=500'
            },
            {
                'name': 'Kitchen Knife Set',
                'description': 'Professional 8-piece kitchen knife set with wooden block. Made from high-carbon stainless steel.',
                'price': 89.99,
                'stock_quantity': 45,
                'category': 'Home & Garden',
                'image_url': 'https://images.unsplash.com/photo-1593618998160-e34014e67546?w=500'
            },
            {
                'name': 'Programming in Python',
                'description': 'Comprehensive guide to Python programming. Perfect for beginners and intermediate learners.',
                'price': 39.99,
                'stock_quantity': 120,
                'category': 'Books',
                'image_url': 'https://images.unsplash.com/photo-1516979187457-637abb4f9353?w=500'
            },
            {
                'name': 'The Art of Web Design',
                'description': 'Learn modern web design principles and best practices. Includes case studies and examples.',
                'price': 44.99,
                'stock_quantity': 90,
                'category': 'Books',
                'image_url': 'https://images.unsplash.com/photo-1532012197267-da84d127e765?w=500'
            },
            {
                'name': 'Yoga Mat Premium',
                'description': 'Extra thick yoga mat with carrying strap. Non-slip surface for safe practice.',
                'price': 29.99,
                'stock_quantity': 150,
                'category': 'Sports',
                'image_url': 'https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f?w=500'
            },
            {
                'name': 'Resistance Bands Set',
                'description': 'Set of 5 resistance bands with different resistance levels. Perfect for home workouts.',
                'price': 24.99,
                'stock_quantity': 200,
                'category': 'Sports',
                'image_url': 'https://images.unsplash.com/photo-1598289431512-b97b0917affc?w=500'
            },
            {
                'name': 'Basketball Official Size',
                'description': 'Official size and weight basketball. Suitable for indoor and outdoor use.',
                'price': 34.99,
                'stock_quantity': 85,
                'category': 'Sports',
                'image_url': 'https://images.unsplash.com/photo-1546519638-68e109498ffc?w=500'
            },
            {
                'name': 'Running Shoes Pro',
                'description': 'Lightweight running shoes with advanced cushioning technology. Available in multiple sizes.',
                'price': 119.99,
                'stock_quantity': 65,
                'category': 'Sports',
                'image_url': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=500'
            },
        ]

        # Distribute products among sellers
        for i, product_data in enumerate(products_data):
            seller = sellers[i % len(sellers)]
            category = categories[product_data.pop('category')]

            product, created = Product.objects.get_or_create(
                name=product_data['name'],
                seller=seller,
                defaults={
                    **product_data,
                    'category': category
                }
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Created product: {product.name} (Seller: {seller.email})'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSuccessfully populated database with {len(products_data)} products!'
            )
        )
