from django.utils import timezone
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.contrib.auth.models import Group as DjangoGroup
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.contrib.auth import get_user_model
import uuid
import json
import hashlib
from decimal import Decimal
import os


class UsersManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)

        if 'role' not in extra_fields:
            extra_fields['role'] = 'buyer'

        if extra_fields['role'] == 'admin':
            extra_fields['is_staff'] = True
            extra_fields['is_superuser'] = False
        elif extra_fields['role'] == 'superadmin':
            extra_fields['is_staff'] = True
            extra_fields['is_superuser'] = True
        else:
            extra_fields['is_staff'] = False
            extra_fields['is_superuser'] = False

        extra_fields['is_active'] = True

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if 'role' not in extra_fields:
            extra_fields['role'] = 'superadmin'

        return self.create_user(email, password, **extra_fields)

    def create_anonymous_user(self):
        anonymous_email = "anonymous@example.com"
        if not self.filter(email=anonymous_email).exists():
            anonymous_user = self.create(
                email=anonymous_email,
                role="buyer",
                is_active=False,
                is_staff=False,
                is_superuser=False,
            )
            anonymous_user.set_unusable_password()
            anonymous_user.save()
            return anonymous_user
        return None


class Users(AbstractBaseUser, PermissionsMixin):
    email = models.CharField(unique=True, max_length=50)
    password = models.CharField(max_length=128)
    ROLE_CHOICES = (
        ('buyer', 'Buyer'),
        ('seller', 'Seller'),
        ('admin', 'Admin'),
        ('superadmin', 'Super Admin'),
    )
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    phonenumber = PhoneNumberField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    objects = UsersManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"User(id={self.id}, email={self.email}, role={self.role})"

    def get_phone_number(self):
        return str(self.phonenumber) if self.phonenumber else None

    @property
    def available_balance(self):
        """Calculate available balance from completed payments"""
        if self.role != 'seller':
            return Decimal('0.00')

        total_earned = SellerPayment.objects.filter(
            seller=self,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        total_withdrawn = CashOut.objects.filter(
            seller=self,
            status='completed'
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        return total_earned - total_withdrawn


class Group(DjangoGroup):
    group_id = models.AutoField(primary_key=True)
    admin = models.ForeignKey(
        'Users',
        on_delete=models.CASCADE,
        related_name='managed_group',
        limit_choices_to={'role': 'admin'},
        null=True,
        blank=True
    )
    superadmin = models.ForeignKey(
        'Users',
        on_delete=models.CASCADE,
        related_name='supervised_groups',
        limit_choices_to={'role': 'superadmin'},
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'groups'

    def __str__(self):
        if self.admin:
            return f"Group(name={self.name}, admin={self.admin.email})"
        elif self.superadmin:
            return f"Group(name={self.name}, superadmin={self.superadmin.email})"
        else:
            return f"Group(name={self.name})"


User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


def product_image_path(instance, filename):
    """Generate upload path for product images"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('products', str(instance.seller.id), filename)


class Product(models.Model):
    seller = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='products',
        limit_choices_to={'role': 'seller'}
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='products'
    )
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    image = models.ImageField(
        upload_to=product_image_path, blank=True, null=True)
    image_url = models.URLField(
        max_length=500, blank=True)  # For external URLs
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - ${self.price}"

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    @property
    def image_display_url(self):
        """Return the appropriate image URL - uploaded or external"""
        if self.image:
            return self.image.url
        return self.image_url or ''


class Cart(models.Model):
    user = models.OneToOneField(
        Users,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'carts'

    def __str__(self):
        return f"Cart for {self.user.email}"

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    quantity = models.IntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cart_items'
        unique_together = ['cart', 'product']

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class Wishlist(models.Model):
    user = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='wishlists'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wishlists'
        unique_together = ['user', 'product']

    def __str__(self):
        return f"{self.user.email} - {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    order_number = models.CharField(max_length=50, unique=True)
    buyer = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    fair_cashier_request_id = models.UUIDField(null=True, blank=True)
    payment_method = models.CharField(
        max_length=20,
        choices=[('online', 'Online'), ('cash', 'Cash'), ('mixed', 'Mixed')],
        default='cash'
    )
    online_payment_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('completed', 'Completed'), 
                 ('failed', 'Failed'), ('partial', 'Partial')],
        default='pending'
    )

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_number} - {self.buyer.email}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_order_number():
        import random
        import string
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(
            string.ascii_uppercase + string.digits, k=6))
        return f"ORD-{timestamp}-{random_str}"

class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )
    seller = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='sold_items'
    )
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=20,
        choices=[('online', 'Online Payment'), ('cash', 'Cash on Delivery')],
        default='cash'
    )
    payment_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed')],
        default='pending'
    )
    payment_options = models.JSONField(
        default=list,
        help_text="Available payment methods for this item, e.g., ['cash'] or ['cash', 'online']"
    )

    class Meta:
        db_table = 'order_items'

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    def save(self, *args, **kwargs):
        self.subtotal = self.price * self.quantity
        # Ensure payment_options is always a list
        if not self.payment_options:
            self.payment_options = ['cash']
        super().save(*args, **kwargs)
    
    @property
    def can_pay_online(self):
        """Check if this item supports online payment"""
        return 'online' in self.payment_options

class SellerPayment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='seller_payments'
    )
    seller = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='payments_received'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seller_payments'

    def __str__(self):
        return f"Payment to {self.seller.email} - ${self.amount}"


class CashOut(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )

    cashout_number = models.CharField(max_length=50, unique=True)
    seller = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='cashouts',
        limit_choices_to={'role': 'seller'}
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    processing_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_amount = models.DecimalField(
        max_digits=10, decimal_places=2)  # Amount after fee
    payment_method = models.CharField(max_length=50, default='bank_transfer')
    # Store bank details, etc.
    payment_details = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        Users,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_cashouts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'cashouts'
        ordering = ['-created_at']

    def __str__(self):
        return f"Cashout {self.cashout_number} - {self.seller.email} - ${self.amount}"

    def save(self, *args, **kwargs):
        if not self.cashout_number:
            self.cashout_number = self.generate_cashout_number()

        # Calculate processing fee (e.g., 2.5%)
        if not self.processing_fee:
            self.processing_fee = self.amount * Decimal('0.025')

        # Calculate net amount
        self.net_amount = self.amount - self.processing_fee

        super().save(*args, **kwargs)

    @staticmethod
    def generate_cashout_number():
        import random
        import string
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(
            string.ascii_uppercase + string.digits, k=6))
        return f"CO-{timestamp}-{random_str}"
