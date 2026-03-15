from django.core.management.base import BaseCommand
from shopping_app.models import Users, Cart, CartItem, Wishlist, Product
import random


class Command(BaseCommand):
    help = "Populate buyers, carts, and wishlists"

    def handle(self, *args, **kwargs):

        buyer_emails = [
            f"buyer{i}@gmail.com"
            for i in range(1, 11)
        ]

        buyers = []

        # -------------------------------
        # Create buyers
        # -------------------------------
        for email in buyer_emails:

            buyer, created = Users.objects.get_or_create(
                email=email,
                defaults={
                    "role": "buyer",
                    "is_staff": False,
                    "is_superuser": False,
                },
            )

            if created:
                buyer.set_password("Buyer.123")
                buyer.save()
                self.stdout.write(self.style.SUCCESS(f"Created buyer {email}"))

            buyers.append(buyer)

        # -------------------------------
        # Create carts
        # -------------------------------
        for buyer in buyers:
            Cart.objects.get_or_create(user=buyer)

        products = list(Product.objects.all())

        # -------------------------------
        # Populate carts
        # -------------------------------
        for buyer in buyers:

            cart = Cart.objects.get(user=buyer)

            cart_products = random.sample(products, 5)

            for product in cart_products:

                CartItem.objects.get_or_create(
                    cart=cart,
                    product=product,
                    defaults={"quantity": random.randint(1, 3)}
                )

        # -------------------------------
        # Populate wishlists
        # -------------------------------
        for buyer in buyers:

            wishlist_products = random.sample(products, 5)

            for product in wishlist_products:

                Wishlist.objects.get_or_create(
                    user=buyer,
                    product=product
                )

        self.stdout.write(
            self.style.SUCCESS(
                "\nBUYER DATA CREATED\n"
                "Buyers: 10\n"
                f"Products available: {len(products)}"
            )
        )