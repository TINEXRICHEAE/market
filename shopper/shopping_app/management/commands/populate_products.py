from django.core.management.base import BaseCommand
from shopping_app.models import Users, Category, Product, SellerVerification
import json
from django.utils import timezone
from pathlib import Path


class Command(BaseCommand):
    help = "Populate sellers, products, and seller KYC data"

    def handle(self, *args, **kwargs):

        # -------------------------------
        # Load KYC dataset
        # -------------------------------
        BASE_DIR = Path(__file__).resolve().parents[3]
        kyc_file = BASE_DIR / "shopping_app/dev_seed_data/sellers_kyc.json"
        with open(kyc_file, "r") as f:
            kyc_data = json.load(f)

        sellers = []

        seller_emails = [
            f"seller{i}@gmail.com"
            for i in range(1, 11)
        ]

        # -------------------------------
        # Create sellers
        # -------------------------------
        for i, email in enumerate(seller_emails):

            seller, created = Users.objects.get_or_create(
                email=email,
                defaults={
                    "role": "seller",
                    "is_staff": False,
                    "is_superuser": False,
                },
            )

            if created:
                seller.set_password("Seller.123")
                seller.save()
                self.stdout.write(self.style.SUCCESS(f"Created seller {email}"))

            sellers.append(seller)

            # -------------------------------
            # Create KYC record
            # -------------------------------
            kyc = kyc_data[i]

            SellerVerification.objects.get_or_create(
                seller=seller,
                defaults={
                    "full_legal_name": kyc["full_legal_name"],
                    "national_id_number": kyc["national_id_number"],
                    "date_of_birth": kyc["date_of_birth"],
                    "phone_number": kyc["phone_number"],
                    "physical_address": kyc["physical_address"],
                    "district": kyc["district"],
                    "country": kyc["country"],

                    "business_name": kyc["business"]["business_name"],
                    "business_registration_no": kyc["business"]["business_registration_no"],
                    "business_type": "individual",
                    "business_address": kyc["business"]["business_address"],
                    "tin_number": kyc["business"]["tin_number"],

                    "national_id_front": kyc["documents"]["national_id_front"],
                    "national_id_back": kyc["documents"]["national_id_back"],
                    "selfie_with_id": kyc["documents"]["selfie_with_id"],
                    "business_cert": kyc["documents"]["business_cert"],
                    "proof_of_address": kyc["documents"]["proof_of_address"],

                    "status": "pending",
                    "zkp_status": "not_registered",
                }
            )

        # -------------------------------
        # Create categories
        # -------------------------------
        categories_data = [
            ("Electronics", "Electronic devices"),
            ("Clothing", "Fashion items"),
            ("Home & Garden", "Home improvement"),
            ("Books", "Educational materials"),
            ("Sports", "Sports equipment"),
        ]

        categories = {}

        for name, desc in categories_data:
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={"description": desc}
            )
            categories[name] = category

        # -------------------------------
        # Product templates
        # -------------------------------
        base_products = [
            ("Bluetooth Headphones", "Electronics", 290000, "https://images.unsplash.com/photo-1505740420928-5e560c06d30e"),
            ("Smart Watch", "Electronics", 1100000, "https://images.unsplash.com/photo-1523275335684-37898b6baf30"),
            ("Laptop Stand", "Electronics", 145000, "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46"),
            ("Wireless Mouse", "Electronics", 95000, "https://images.unsplash.com/photo-1587829741301-dc798b83add3"),
            ("Mechanical Keyboard", "Electronics", 345000, "https://images.unsplash.com/photo-1511467687858-23d96c32e4ae"),

            ("Cotton T Shirt", "Clothing", 110000, "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab"),
            ("Denim Jeans", "Clothing", 220000, "https://images.unsplash.com/photo-1542272604-787c3835535d"),
            ("Winter Jacket", "Clothing", 475000, "https://images.unsplash.com/photo-1551028719-00167b16eac5"),
            ("Running Shoes", "Clothing", 435000, "https://images.unsplash.com/photo-1542291026-7eec264c27ff"),
            ("Baseball Cap", "Clothing", 85000, "https://images.unsplash.com/photo-1521369909029-2afed882baee"),

            ("Indoor Plant", "Home & Garden", 165000, "https://images.unsplash.com/photo-1485955900006-10f4d324d411"),
            ("LED Desk Lamp", "Home & Garden", 128000, "https://images.unsplash.com/photo-1507473885765-e6ed057f782c"),
            ("Kitchen Knife Set", "Home & Garden", 330000, "https://images.unsplash.com/photo-1593618998160-e34014e67546"),
            ("Office Chair", "Home & Garden", 890000, "https://images.unsplash.com/photo-1580480055273-228ff5388ef8"),
            ("Coffee Maker", "Home & Garden", 650000, "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085"),

            ("Python Programming Book", "Books", 145000, "https://images.unsplash.com/photo-1516979187457-637abb4f9353"),
            ("Web Design Book", "Books", 165000, "https://images.unsplash.com/photo-1512820790803-83ca734da794"),
            ("Data Science Handbook", "Books", 175000, "https://images.unsplash.com/photo-1524995997946-a1c2e315a42f"),
            ("Machine Learning Guide", "Books", 195000, "https://images.unsplash.com/photo-1532012197267-da84d127e765"),
            ("Startup Business Book", "Books", 155000, "https://images.unsplash.com/photo-1519681393784-d120267933ba"),

            ("Yoga Mat", "Sports", 110000, "https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f"),
            ("Resistance Bands", "Sports", 90000, "https://images.unsplash.com/photo-1599058917765-a780eda07a3e"),
            ("Basketball", "Sports", 128000, "https://images.unsplash.com/photo-1519861531473-9200262188bf"),
            ("Football", "Sports", 120000, "https://images.unsplash.com/photo-1574629810360-7efbbe195018"),
            ("Dumbbell Set", "Sports", 280000, "https://images.unsplash.com/photo-1517838277536-f5f99be501cd"),
        ]

        # -------------------------------
        # Create 5 products per seller
        # -------------------------------
        product_count = 0

        for seller_index, seller in enumerate(sellers):

            for i in range(5):

                template = base_products[(seller_index * 5 + i) % len(base_products)]

                name, category_name, price, image = template

                Product.objects.get_or_create(
                    seller=seller,
                    name=f"{name} - Seller {seller_index+1}-{i+1}",
                    defaults={
                        "description": f"{name} sold by seller {seller_index+1}",
                        "price": price,
                        "stock_quantity": 50 + i * 10,
                        "category": categories[category_name],
                        "image_url": image,
                    }
                )

                product_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCreated {len(sellers)} sellers and {product_count} products."
            )
        )