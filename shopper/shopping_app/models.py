from django.utils import timezone
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField
from django.contrib.auth.models import Group as DjangoGroup
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
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
        ('partially_delivered', 'Partially Delivered'),
        ('delivered', 'Delivered'),
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
        choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('deposited', 'Payment Reseved')],
        default='pending'
    )
    payment_options = models.JSONField(
        default=list,
        help_text="Available payment methods for this item, e.g., ['cash'] or ['cash', 'online']"
    )
    TRACKING_STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('reviewed', 'Reviewed'),
        ('confirmed', 'Confirmed'),
        ('packed', 'Packed'),
        ('dispatched', 'Dispatched'),
        ('in_transit', 'In Transit'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered_by_seller', 'Marked Delivered'),
        ('delivered', 'Delivery Confirmed'),
        ('disputed', 'Disputed'),
        ('cancelled', 'Cancelled'),
    )
    tracking_status = models.CharField(max_length=30, choices=TRACKING_STATUS_CHOICES, default='pending')
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    dispatch_date = models.DateTimeField(null=True, blank=True)
    estimated_delivery = models.DateTimeField(null=True, blank=True)
    delivery_marked_at = models.DateTimeField(null=True, blank=True)
    delivery_confirmed_at = models.DateTimeField(null=True, blank=True)
    delivery_notes = models.TextField(blank=True, null=True)
    has_dispute = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def tracking_status_display_verbose(self):
        return dict(self.TRACKING_STATUS_CHOICES).get(self.tracking_status, self.tracking_status)

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


# ===================== OrderItemTracking =====================


class OrderItemTracking(models.Model):
    """
    Tracks the history of status changes for each order item.
    Provides a granular audit trail for order tracking pages.
    """
    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name='tracking_history'
    )
    status = models.CharField(max_length=30)
    notes = models.TextField(blank=True, null=True)
    updated_by_role = models.CharField(
        max_length=20,
        choices=[('seller', 'Seller'), ('buyer', 'Buyer'), ('system', 'System'), ('admin', 'Admin')],
        default='system'
    )
    updated_by = models.ForeignKey(
        Users,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='tracking_updates'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_item_tracking'
        ordering = ['-created_at']

    def __str__(self):
        return f"Tracking({self.order_item.id}: {self.status} at {self.created_at})"



# ===================== DeliveryConfirmation =====================


class DeliveryConfirmation(models.Model):
    """
    Buyer's delivery confirmation/approval for an order.
    One record per order when seller marks items as delivered.
    Contains per-item approval/dispute data.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='delivery_confirmations'
    )
    buyer = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='delivery_confirmations'
    )
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'delivery_confirmations'
        ordering = ['-created_at']

    def __str__(self):
        return f"DeliveryConfirmation(Order {self.order.order_number}, Buyer {self.buyer.email})"



# ===================== OrderDispute =====================


class OrderDispute(models.Model):
    """
    Dispute on a specific order item within the shopping app.
    If the item was paid online (payment_method='online', payment_status='paid'),
    the dispute is forwarded to the payment app (Fair Cashier).
    If it's cash-on-delivery, the dispute stays local for the shopping app admin.
    """
    COMPLAINT_CHOICES = (
        ('not_as_ordered', 'Not the specified item by order'),
        ('damaged', 'Item is damaged'),
        ('wrong_details', 'Wrong details/measurements'),
        ('wrong_quantity', 'Wrong quantity received'),
        ('inconsistent_payment', 'Inconsistent payment status with delivery'),
        ('suspicious_seller', 'Suspicious seller/delivery person'),
        ('counterfeit', 'Suspected counterfeit product'),
        ('missing_parts', 'Missing parts or accessories'),
        ('wrong_color_size', 'Wrong color or size'),
        ('expired_product', 'Product expired or near expiry'),
        ('other', 'Other'),
    )

    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('escalated', 'Escalated to Admin'),
        ('resolved_with_refund', 'Resolved With Refund'),
        ('resolved_without_refund', 'Resolved Without Refund'),
    )

    dispute_id = models.AutoField(primary_key=True)
    order_item = models.OneToOneField(
        OrderItem,
        on_delete=models.CASCADE,
        related_name='dispute'
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='disputes'
    )
    buyer = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='shopping_disputes_filed'
    )
    seller = models.ForeignKey(
        Users,
        on_delete=models.CASCADE,
        related_name='shopping_disputes_received'
    )
    complaint_type = models.CharField(max_length=30, choices=COMPLAINT_CHOICES)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='submitted')

    # Payment app integration
    is_online_payment = models.BooleanField(default=False)
    payment_app_dispute_id = models.IntegerField(
        null=True, blank=True,
        help_text="Dispute ID in the payment app (Fair Cashier)"
    )
    payment_app_status = models.CharField(
        max_length=30, blank=True, null=True,
        help_text="Synced status from payment app"
    )
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refund_processed_at = models.DateTimeField(null=True, blank=True)

    # Resolution
    admin_notes = models.TextField(blank=True, null=True)
    resolved_by = models.ForeignKey(
        Users,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='shopping_disputes_resolved'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'order_disputes'
        ordering = ['-created_at']

    def __str__(self):
        return f"OrderDispute(#{self.dispute_id}, Item {self.order_item.id}, {self.get_status_display()})"

    @property
    def is_resolved(self):
        return self.status in ('resolved_with_refund', 'resolved_without_refund')

    @property
    def needs_payment_app(self):
        """Whether this dispute should be forwarded to the payment app."""
        return (
            self.order_item.payment_method == 'online'
            and self.order_item.payment_status == 'paid'
        )




def seller_doc_upload_path(instance, filename):
    """Store documents under media/seller_kyc/<user_id>/<filename>"""
    ext = filename.rsplit('.', 1)[-1]
    safe_name = f"{uuid.uuid4()}.{ext}"
    return f"seller_kyc/{instance.seller.id}/{safe_name}"


class SellerVerification(models.Model):
    """
    Full KYC record for a seller.
    OneToOne with Users (role='seller').
    Tracks both shopping-app KYC approval AND ZKP Merkle registration.
    """

    class VerificationStatus(models.TextChoices):
        INCOMPLETE = 'incomplete', 'Incomplete'
        PENDING    = 'pending',    'Pending Review'
        APPROVED   = 'approved',   'Approved'
        REJECTED   = 'rejected',   'Rejected'

    class ZKPStatus(models.TextChoices):
        NOT_REGISTERED = 'not_registered', 'Not Registered'
        REGISTERED     = 'registered',     'Registered in Merkle Tree'
        FAILED         = 'failed',         'Registration Failed'

    # ── Core link ─────────────────────────────────────────────────────────────
    seller = models.OneToOneField(
        'Users',          # same app — adjust to just 'Users' if merged into models.py
        on_delete=models.CASCADE,
        related_name='kyc_verification',
        limit_choices_to={'role': 'seller'},
    )
    verification_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # ── Personal information ──────────────────────────────────────────────────
    full_legal_name    = models.CharField(max_length=255)
    national_id_number = models.CharField(max_length=100, unique=True)
    date_of_birth      = models.DateField()
    phone_number       = models.CharField(max_length=30)
    physical_address   = models.TextField()
    district           = models.CharField(max_length=100)
    country            = models.CharField(max_length=100, default='Uganda')

    # ── Business information ──────────────────────────────────────────────────
    business_name            = models.CharField(max_length=255)
    business_registration_no = models.CharField(max_length=100, blank=True)
    business_type            = models.CharField(
        max_length=50,
        choices=[
            ('individual',  'Individual / Sole Trader'),
            ('partnership', 'Partnership'),
            ('company',     'Registered Company'),
            ('ngo',         'NGO / Non-profit'),
        ],
        default='individual',
    )
    business_address = models.TextField(blank=True)
    tin_number       = models.CharField(max_length=100, blank=True, verbose_name='TIN Number')

    # ── Document uploads ──────────────────────────────────────────────────────
    national_id_front = models.FileField(upload_to=seller_doc_upload_path)
    national_id_back  = models.FileField(upload_to=seller_doc_upload_path, blank=True, null=True)
    selfie_with_id    = models.FileField(upload_to=seller_doc_upload_path, blank=True, null=True)
    business_cert     = models.FileField(upload_to=seller_doc_upload_path, blank=True, null=True,
                                         verbose_name='Business Registration Certificate')
    proof_of_address  = models.FileField(upload_to=seller_doc_upload_path, blank=True, null=True)

    # ── KYC review ───────────────────────────────────────────────────────────
    status      = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.INCOMPLETE,
        db_index=True,
    )
    admin_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        'Users',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='kyc_reviews_given',
        limit_choices_to={'role__in': ['admin', 'superadmin']},
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # ── ZKP registration ──────────────────────────────────────────────────────
    zkp_status           = models.CharField(
        max_length=20,
        choices=ZKPStatus.choices,
        default=ZKPStatus.NOT_REGISTERED,
        db_index=True,
    )
    zkp_commitment_hash  = models.CharField(max_length=512, blank=True,
                                            help_text='Merkle leaf commitment returned by Strapi ZKP')
    zkp_merkle_root      = models.CharField(max_length=512, blank=True)
    zkp_registered_at    = models.DateTimeField(null=True, blank=True)
    zkp_last_verified_at = models.DateTimeField(null=True, blank=True)
    zkp_proof_cached     = models.JSONField(null=True, blank=True,
                                            help_text='Latest cached proof object from Strapi')

    zkp_leaf_index = models.IntegerField(
        null=True, blank=True,
        help_text='Leaf index in the Merkle tree (from Strapi registration)',
    )
    zkp_block_number = models.IntegerField(
        null=True, blank=True,
        help_text='Block number at time of Merkle tree registration',
    )
    zkp_public_signals = models.JSONField(
        null=True, blank=True,
        help_text='Public signals from PLONK KYC proof generation',
    )
    # ── Timestamps ────────────────────────────────────────────────────────────
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'seller_kyc_verifications'
        verbose_name = 'Seller KYC Verification'
        verbose_name_plural = 'Seller KYC Verifications'
        ordering = ['-submitted_at']

    def __str__(self):
        return f"KYC [{self.status}] — {self.seller.email}"

    # ── Convenience properties ────────────────────────────────────────────────
    @property
    def is_approved(self):
        return self.status == self.VerificationStatus.APPROVED

    @property
    def is_zkp_registered(self):
        return self.zkp_status == self.ZKPStatus.REGISTERED

    @property
    def is_fully_verified(self):
        """True only when KYC approved AND in ZKP Merkle tree."""
        return self.is_approved and self.is_zkp_registered

    # ── Lifecycle helpers ─────────────────────────────────────────────────────
    def mark_approved(self, admin_user=None):
        self.status      = self.VerificationStatus.APPROVED
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])

    def mark_rejected(self, notes='', admin_user=None):
        self.status      = self.VerificationStatus.REJECTED
        self.admin_notes = notes
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=['status', 'admin_notes', 'reviewed_by', 'reviewed_at', 'updated_at'])

    def record_zkp_registration(self, commitment_hash, merkle_root, proof=None):
        self.zkp_status          = self.ZKPStatus.REGISTERED
        self.zkp_commitment_hash = commitment_hash
        self.zkp_merkle_root     = merkle_root
        self.zkp_registered_at   = timezone.now()
        if proof:
            self.zkp_proof_cached = proof
        self.save(update_fields=[
            'zkp_status', 'zkp_commitment_hash', 'zkp_merkle_root',
            'zkp_registered_at', 'zkp_proof_cached', 'updated_at',
        ])




class BalanceProofVerification(models.Model):
    """
    Stores Shopping App's independent verification of balance proofs
    generated by the Payment App. Buyer wallet balance is NEVER stored here.
    """
    TIER_CHOICES = (
        ('green', 'Green — buyer can pay all items'),
        ('amber', 'Amber — buyer can pay some items'),
        ('red', 'Red — buyer cannot pay any items'),
        ('unknown', 'Unknown'),
    )

    order_number = models.CharField(max_length=50, db_index=True, help_text='Matches Order.order_number')
    seller_email = models.EmailField(db_index=True)

    tier_result = models.CharField(max_length=10, choices=TIER_CHOICES, default='unknown')
    items_payable = models.IntegerField(default=0)
    total_items = models.IntegerField(default=0)
    binary_bracket = models.IntegerField(default=0, help_text='Power-of-two bracket from proof')

    verified = models.BooleanField(default=False, help_text='True if Strapi confirmed proof valid')
    verified_at = models.DateTimeField(null=True, blank=True)

    proof = models.JSONField(null=True, blank=True, help_text='Groth16 proof for re-verification')
    public_signals = models.JSONField(null=True, blank=True)
    item_details = models.JSONField(
        null=True, blank=True,
        help_text='Per-item payability from Payment App: [{shopping_order_item_id, amount, payable}]'
    )

    expires_at = models.DateTimeField(null=True, blank=True)
    refresh_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'balance_proof_verifications'
        unique_together = [('order_number', 'seller_email')]
        ordering = ['-created_at']

    def __str__(self):
        return f"BalanceProof [{self.tier_result}] order={self.order_number} seller={self.seller_email}"

    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return self.expires_at < timezone.now()

