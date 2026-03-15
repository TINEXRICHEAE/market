from django.core.management.base import BaseCommand
from django.core.management import call_command

from shopping_app.models import (
    Users,
    Product,
    Category,
    Cart,
    CartItem,
    Wishlist,
    SellerVerification,
)


class Command(BaseCommand):
    help = "Reset development data and repopulate sellers, products, buyers, carts, wishlists and KYC"

    def handle(self, *args, **kwargs):

        self.stdout.write(self.style.WARNING("\nRESETTING DEVELOPMENT DATABASE...\n"))

        # -----------------------------
        # Delete marketplace data
        # -----------------------------
        CartItem.objects.all().delete()
        Cart.objects.all().delete()
        Wishlist.objects.all().delete()

        Product.objects.all().delete()
        Category.objects.all().delete()

        SellerVerification.objects.all().delete()

        # -----------------------------
        # Delete test users
        # -----------------------------
        Users.objects.filter(email__startswith="seller").delete()
        Users.objects.filter(email__startswith="buyer").delete()

        self.stdout.write(self.style.SUCCESS("Old dev data cleared.\n"))

        # -----------------------------
        # Rebuild dataset
        # -----------------------------
        self.stdout.write(self.style.SUCCESS("Repopulating sellers and products...\n"))
        call_command("populate_products")

        self.stdout.write(self.style.SUCCESS("\nRepopulating buyers...\n"))
        call_command("populate_buyers")

        self.stdout.write(
            self.style.SUCCESS(
                "\n" +
                "=" * 50 +
                "\nDEV DATABASE RESET COMPLETE\n" +
                "=" * 50 +
                "\nSellers: 10\n"
                "Products: 50\n"
                "Buyers: 10\n"
                "Carts: 10\n"
                "Cart Items: ~50\n"
                "Wishlists: ~50\n"
                "Seller KYC Records: 10\n"
                "\nSeller login:\n"
                "seller1@gmail.com - seller10@gmail.com\n"
                "Password: Seller.123\n"
                "\nBuyer login:\n"
                "buyer1@gmail.com - buyer10@gmail.com\n"
                "Password: buyer123\n"
                "=" * 50
            )
        )