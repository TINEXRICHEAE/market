from django.contrib import admin
from django.contrib.auth.models import Group as BuiltInGroup
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from django.db.models import Count, Q
from django.contrib import messages
from django.http import HttpResponseRedirect
from guardian.admin import GuardedModelAdmin
from guardian.shortcuts import get_objects_for_user
from .models import (
    Users, Group, Category, Product, Cart, CartItem,
    Wishlist, Order, OrderItem, OrderItemTracking,
    DeliveryConfirmation, OrderDispute, SellerVerification,
)

import logging
logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# ZKP REGISTRATION HELPER — called after admin approves KYC
# ═════════════════════════════════════════════════════════════════════════════

def _auto_register_zkp(kyc_obj, request=None):
    """
    Automatically register a seller in the ZKP Merkle tree after KYC approval.
    Non-blocking — if it fails, KYC is still approved. Admin sees a warning.
    """
    from .zkp_client import ZKPClient, encode_kyc_fields

    if kyc_obj.zkp_status == 'registered':
        return  # Already registered

    try:
        encoded = encode_kyc_fields({
            'national_id': kyc_obj.national_id_number,
            'date_of_birth': kyc_obj.date_of_birth.strftime('%Y%m%d'),
            'business_license': kyc_obj.business_registration_no or '',
            'tin': kyc_obj.tin_number or '',
            'business_address': kyc_obj.business_address or kyc_obj.physical_address or '',
        })

        client = ZKPClient()

        # 1. Register in Merkle tree
        reg = client.register_seller(
            national_id=encoded['national_id'],
            date_of_birth=encoded['date_of_birth'],
            business_license=encoded['business_license'],
            tin=encoded['tin'],
            business_address=encoded['business_address'],
        )

        commitment = reg.get('commitment', '')
        leaf_index = reg.get('leaf_index')
        kyc_root = reg.get('kyc_root', '')
        block_number = reg.get('block_number')

        # 2. Generate PLONK proof
        proof = None
        public_signals = None
        try:
            pr = client.generate_kyc_proof(
                national_id=encoded['national_id'],
                date_of_birth=encoded['date_of_birth'],
                business_license=encoded['business_license'],
                tin=encoded['tin'],
                business_address=encoded['business_address'],
                leaf_index=leaf_index,
            )
            proof = pr.get('proof')
            public_signals = pr.get('publicSignals')
        except Exception as e:
            logger.warning(f"ZKP proof generation failed for {kyc_obj.seller.email} (tree OK): {e}")

        # 3. Store on SellerVerification
        kyc_obj.record_zkp_registration(
            commitment_hash=commitment,
            merkle_root=kyc_root,
            proof=proof,
        )
        kyc_obj.zkp_leaf_index = leaf_index
        kyc_obj.zkp_block_number = block_number
        kyc_obj.zkp_public_signals = public_signals
        kyc_obj.save(update_fields=[
            'zkp_leaf_index', 'zkp_block_number', 'zkp_public_signals', 'updated_at',
        ])

        logger.info(
            f"Auto ZKP registration OK: {kyc_obj.seller.email}, "
            f"leaf={leaf_index}, commitment={commitment[:20]}..."
        )
        if request:
            messages.success(
                request,
                f"ZKP registered for {kyc_obj.seller.email} "
                f"(leaf #{leaf_index})"
            )

    except Exception as e:
        logger.error(f"Auto ZKP registration FAILED for {kyc_obj.seller.email}: {e}")
        kyc_obj.zkp_status = SellerVerification.ZKPStatus.FAILED
        kyc_obj.save(update_fields=['zkp_status', 'updated_at'])
        if request:
            messages.warning(
                request,
                f"KYC approved but ZKP registration failed for "
                f"{kyc_obj.seller.email}: {e}. "
                f"Use 'Register ZKP' action to retry."
            )


# ═════════════════════════════════════════════════════════════════════════════
# GROUP ADMIN (unchanged)
# ═════════════════════════════════════════════════════════════════════════════

class GroupAdmin(GuardedModelAdmin, BaseGroupAdmin):
    list_display = ('name', 'admin_display', 'superadmin_display', 'member_count', 'permission_count')
    search_fields = ('name', 'admin__email', 'superadmin__email')
    list_filter = ('admin__role', 'superadmin__role')
    filter_horizontal = ('permissions',)
    ordering = ('name',)

    fieldsets = (
        ('Basic Information', {'fields': ('name',)}),
        ('Management', {'fields': ('admin', 'superadmin'), 'description': 'Assign administrators'}),
        ('Permissions', {'fields': ('permissions',), 'classes': ('collapse',)}),
    )

    def admin_display(self, obj):
        if obj.admin:
            return format_html('<span style="color:#0066cc;"><strong>{}</strong></span>', obj.admin.email)
        return format_html('<span style="color:#999;">—</span>')
    admin_display.short_description = 'Admin'

    def superadmin_display(self, obj):
        if obj.superadmin:
            return format_html('<span style="color:#cc0000;"><strong>{}</strong></span>', obj.superadmin.email)
        return format_html('<span style="color:#999;">—</span>')
    superadmin_display.short_description = 'Super Admin'

    def member_count(self, obj):
        return obj.user_set.count()
    member_count.short_description = 'Members'

    def permission_count(self, obj):
        return obj.permissions.count()
    permission_count.short_description = 'Permissions'

    def has_module_permission(self, request):
        if super().has_module_permission(request):
            return True
        return self.get_model_objects(request).exists()

    def get_queryset(self, request):
        if request.user.is_superuser:
            return super().get_queryset(request).select_related('admin', 'superadmin')
        return self.get_model_objects(request).select_related('admin', 'superadmin')

    def get_model_objects(self, request, action=None, klass=None):
        opts = self.opts
        actions = [action] if action else ['view', 'change', 'delete']
        klass = klass if klass else opts.model
        model_name = klass._meta.model_name
        return get_objects_for_user(
            user=request.user,
            perms=[f'{opts.app_label}.{perm}_{model_name}' for perm in actions],
            klass=klass, any_perm=True,
        )

    def has_permission(self, request, obj, action):
        opts = self.opts
        code_name = f'{action}_{opts.model_name}'
        if obj:
            return request.user.has_perm(f'{opts.app_label}.{code_name}', obj)
        return self.get_model_objects(request).exists()

    def has_view_permission(self, request, obj=None):
        return self.has_permission(request, obj, 'view')
    def has_change_permission(self, request, obj=None):
        return self.has_permission(request, obj, 'change')
    def has_delete_permission(self, request, obj=None):
        return self.has_permission(request, obj, 'delete')


# ═════════════════════════════════════════════════════════════════════════════
# USERS ADMIN (unchanged except kyc_badge)
# ═════════════════════════════════════════════════════════════════════════════

@admin.register(Users)
class UsersAdmin(GuardedModelAdmin, UserAdmin):
    list_display = (
        'id', 'email', 'role_badge', 'phone_display',
        'kyc_badge', 'status_display', 'last_login', 'date_joined_display',
    )
    search_fields = ('email', 'phonenumber')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser', 'created_at')
    ordering = ('-created_at',)
    filter_horizontal = ('user_permissions', 'groups')

    fieldsets = (
        ('Account Information', {'fields': ('email', 'password'), 'classes': ('wide',)}),
        ('Personal Information', {'fields': ('role', 'phonenumber'), 'classes': ('wide',)}),
        ('Group Membership', {'fields': ('groups',), 'classes': ('collapse',)}),
        ('Permissions & Status', {'fields': ('is_active', 'is_staff', 'is_superuser', 'user_permissions'), 'classes': ('collapse',)}),
        ('Important Dates', {'fields': ('last_login', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
    )
    add_fieldsets = (
        ('Create New User', {'classes': ('wide',), 'fields': ('email', 'password1', 'password2', 'role', 'phonenumber', 'groups')}),
        ('Permissions (Optional)', {'classes': ('collapse',), 'fields': ('user_permissions',)}),
    )
    readonly_fields = ('created_at', 'updated_at', 'last_login')

    def role_badge(self, obj):
        colors = {'buyer': '#28a745', 'seller': '#17a2b8', 'admin': '#ffc107', 'superadmin': '#dc3545'}
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:3px;font-size:11px;">{}</span>',
            colors.get(obj.role, '#6c757d'), obj.get_role_display(),
        )
    role_badge.short_description = 'Role'

    def kyc_badge(self, obj):
        if obj.role != 'seller':
            return format_html('<span style="color:#999;font-size:11px;">—</span>')
        try:
            kyc = obj.kyc_verification
        except SellerVerification.DoesNotExist:
            return format_html('<span style="background:#6c757d;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;">No KYC</span>')
        kyc_colors = {'incomplete': '#6c757d', 'pending': '#f59e0b', 'approved': '#10b981', 'rejected': '#ef4444'}
        zkp_colors = {'not_registered': '#6c757d', 'registered': '#10b981', 'failed': '#ef4444'}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;margin-right:4px;">KYC: {}</span>'
            '<span style="background:{};color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;">ZKP: {}</span>',
            kyc_colors.get(kyc.status, '#6c757d'), kyc.get_status_display(),
            zkp_colors.get(kyc.zkp_status, '#6c757d'), kyc.get_zkp_status_display(),
        )
    kyc_badge.short_description = 'KYC / ZKP'

    def phone_display(self, obj):
        if obj.phonenumber:
            return format_html('<span style="font-family:monospace;">{}</span>', obj.phonenumber)
        return format_html('<span style="color:#999;">—</span>')
    phone_display.short_description = 'Phone'

    def status_display(self, obj):
        if obj.is_active:
            if obj.is_superuser:
                return format_html('<span style="color:#dc3545;">●</span> Super User')
            elif obj.is_staff:
                return format_html('<span style="color:#ffc107;">●</span> Staff')
            return format_html('<span style="color:#28a745;">●</span> Active')
        return format_html('<span style="color:#6c757d;">●</span> Inactive')
    status_display.short_description = 'Status'

    def date_joined_display(self, obj):
        return obj.created_at.strftime('%b %d, %Y')
    date_joined_display.short_description = 'Date Joined'

    def save_model(self, request, obj, form, change):
        if not change:
            if obj.role == 'admin':
                obj.is_staff = True; obj.is_superuser = False
            elif obj.role == 'superadmin':
                obj.is_staff = True; obj.is_superuser = True
            else:
                obj.is_staff = False; obj.is_superuser = False
            obj.is_active = True
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if not request.user.is_superuser:
            for f in ('role', 'is_superuser', 'user_permissions', 'groups'):
                if f in form.base_fields:
                    form.base_fields[f].disabled = True
        return form

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .exclude(email='anonymous@example.com')
            .prefetch_related('groups')
            .select_related('kyc_verification')
        )


# ═════════════════════════════════════════════════════════════════════════════
# CATEGORY / PRODUCT / CART / WISHLIST (unchanged)
# ═════════════════════════════════════════════════════════════════════════════

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at')
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'category', 'price', 'stock_quantity', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'seller')
    search_fields = ('name', 'description')
    list_editable = ('price', 'stock_quantity', 'is_active')
    ordering = ('-created_at',)

class CartItemInline(admin.TabularInline):
    model = CartItem; extra = 0; readonly_fields = ('added_at',)

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_items', 'total_price', 'created_at')
    search_fields = ('user__email',)
    inlines = [CartItemInline]
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('user__email', 'product__name')


# ═════════════════════════════════════════════════════════════════════════════
# ORDER (unchanged)
# ═════════════════════════════════════════════════════════════════════════════

class OrderItemInline(admin.TabularInline):
    model = OrderItem; extra = 0; readonly_fields = ('subtotal', 'updated_at')
    fields = ('product', 'seller', 'quantity', 'price', 'subtotal', 'payment_method', 'payment_status', 'tracking_status', 'updated_at')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'buyer', 'total_amount', 'status', 'payment_method', 'online_payment_status', 'created_at')
    list_filter = ('status', 'payment_method', 'online_payment_status', 'created_at')
    search_fields = ('order_number', 'buyer__email')
    readonly_fields = ('order_number', 'created_at', 'updated_at')
    inlines = [OrderItemInline]

@admin.register(OrderItemTracking)
class OrderItemTrackingAdmin(admin.ModelAdmin):
    list_display = ('order_item', 'status', 'updated_by_role', 'updated_by', 'created_at')
    list_filter = ('status', 'updated_by_role', 'created_at')
    readonly_fields = ('created_at',)

@admin.register(DeliveryConfirmation)
class DeliveryConfirmationAdmin(admin.ModelAdmin):
    list_display = ('order', 'buyer', 'is_submitted', 'submitted_at', 'created_at')
    list_filter = ('is_submitted', 'created_at')
    readonly_fields = ('created_at', 'updated_at')


# ═════════════════════════════════════════════════════════════════════════════
# ORDER DISPUTE (unchanged)
# ═════════════════════════════════════════════════════════════════════════════

@admin.register(OrderDispute)
class OrderDisputeAdmin(admin.ModelAdmin):
    list_display = (
        'dispute_id', 'order_link', 'buyer', 'seller',
        'complaint_type', 'status_badge', 'is_online_payment',
        'payment_app_dispute_id', 'created_at',
    )
    list_filter = ('status', 'complaint_type', 'is_online_payment', 'created_at')
    search_fields = ('order__order_number', 'buyer__email', 'seller__email', 'description')
    readonly_fields = ('created_at', 'updated_at', 'refund_processed_at', 'payment_app_dispute_id', 'payment_app_status')
    raw_id_fields = ('order_item', 'order', 'buyer', 'seller', 'resolved_by')
    actions = ['mark_under_review', 'mark_escalated']

    fieldsets = (
        ('Dispute Details', {'fields': ('order_item', 'order', 'buyer', 'seller', 'complaint_type', 'description', 'status')}),
        ('Payment App Integration', {'fields': ('is_online_payment', 'payment_app_dispute_id', 'payment_app_status', 'refund_amount', 'refund_processed_at'), 'classes': ('collapse',)}),
        ('Resolution', {'fields': ('admin_notes', 'resolved_by', 'resolved_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def order_link(self, obj):
        url = reverse('admin:shopping_app_order_change', args=[obj.order.id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
    order_link.short_description = 'Order'

    def status_badge(self, obj):
        colors = {'submitted': '#f59e0b', 'under_review': '#3b82f6', 'escalated': '#ef4444', 'resolved_with_refund': '#10b981', 'resolved_without_refund': '#6b7280'}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:3px;font-size:11px;">{}</span>',
            colors.get(obj.status, '#6b7280'), obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

    @admin.action(description='Mark selected disputes as Under Review')
    def mark_under_review(self, request, queryset):
        updated = queryset.filter(status='submitted').update(status='under_review')
        self.message_user(request, f'{updated} dispute(s) marked as Under Review.')

    @admin.action(description='Escalate selected disputes to Admin')
    def mark_escalated(self, request, queryset):
        updated = queryset.exclude(status__in=['resolved_with_refund', 'resolved_without_refund']).update(status='escalated')
        self.message_user(request, f'{updated} dispute(s) escalated.')


# ═════════════════════════════════════════════════════════════════════════════
# SELLER KYC VERIFICATION — with auto ZKP registration
# ═════════════════════════════════════════════════════════════════════════════

@admin.register(SellerVerification)
class SellerVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'seller_email', 'full_legal_name', 'business_name',
        'business_type', 'status_badge', 'zkp_status_badge',
        'submitted_at', 'reviewed_at',
    ]
    list_filter = ['status', 'zkp_status', 'business_type', 'country', 'district']
    search_fields = [
        'seller__email', 'full_legal_name',
        'national_id_number', 'business_name', 'tin_number',
    ]
    readonly_fields = [
        'verification_id', 'submitted_at', 'updated_at',
        'zkp_commitment_hash', 'zkp_merkle_root',
        'zkp_registered_at', 'zkp_last_verified_at', 'zkp_proof_cached',
        'zkp_leaf_index', 'zkp_block_number', 'zkp_public_signals',
    ]
    raw_id_fields = ['seller', 'reviewed_by']
    actions = ['approve_and_register_zkp', 'approve_selected', 'reject_selected', 'register_zkp_selected']

    fieldsets = (
        ('Seller Account', {'fields': ('seller', 'verification_id')}),
        ('Personal Information', {'fields': (
            'full_legal_name', 'national_id_number', 'date_of_birth',
            'phone_number', 'physical_address', 'district', 'country',
        )}),
        ('Business Information', {'fields': (
            'business_name', 'business_registration_no', 'business_type',
            'business_address', 'tin_number',
        )}),
        ('Documents', {'fields': (
            'national_id_front', 'national_id_back', 'selfie_with_id',
            'business_cert', 'proof_of_address',
        )}),
        ('KYC Review', {'fields': ('status', 'admin_notes', 'reviewed_by', 'reviewed_at')}),
        ('ZKP Registration', {
            'fields': (
                'zkp_status', 'zkp_commitment_hash', 'zkp_merkle_root',
                'zkp_leaf_index', 'zkp_block_number',
                'zkp_registered_at', 'zkp_last_verified_at',
                'zkp_proof_cached', 'zkp_public_signals',
            ),
            'classes': ('collapse',),
        }),
        ('Timestamps', {'fields': ('submitted_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def seller_email(self, obj):
        return obj.seller.email
    seller_email.short_description = 'Seller Email'
    seller_email.admin_order_field = 'seller__email'

    def status_badge(self, obj):
        colors = {'incomplete': '#6c757d', 'pending': '#f59e0b', 'approved': '#10b981', 'rejected': '#ef4444'}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:4px;font-size:11px;">{}</span>',
            colors.get(obj.status, '#6c757d'), obj.get_status_display(),
        )
    status_badge.short_description = 'KYC Status'

    def zkp_status_badge(self, obj):
        colors = {'not_registered': '#6c757d', 'registered': '#10b981', 'failed': '#ef4444'}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;border-radius:4px;font-size:11px;">{}</span>',
            colors.get(obj.zkp_status, '#6c757d'), obj.get_zkp_status_display(),
        )
    zkp_status_badge.short_description = 'ZKP Status'

    # ── PRIMARY ACTION: Approve KYC + auto-register ZKP ──────────────

    @admin.action(description='✅ Approve KYC + Register ZKP (recommended)')
    def approve_and_register_zkp(self, request, queryset):
        approved = 0
        zkp_ok = 0
        zkp_fail = 0
        for obj in queryset.filter(status__in=['pending', 'incomplete']):
            obj.mark_approved(admin_user=request.user)
            approved += 1
            # Auto-trigger ZKP registration
            _auto_register_zkp(obj, request)
            if obj.zkp_status == 'registered':
                zkp_ok += 1
            else:
                zkp_fail += 1

        msg = f'{approved} seller(s) KYC approved.'
        if zkp_ok:
            msg += f' {zkp_ok} ZKP registered.'
        if zkp_fail:
            msg += f' {zkp_fail} ZKP failed (can retry with "Register ZKP" action).'
        self.message_user(request, msg, messages.SUCCESS if not zkp_fail else messages.WARNING)

    # ── Approve only (no ZKP) ────────────────────────────────────────

    @admin.action(description='✅ Approve KYC only (no ZKP)')
    def approve_selected(self, request, queryset):
        count = 0
        for obj in queryset.filter(status__in=['pending', 'incomplete']):
            obj.mark_approved(admin_user=request.user)
            count += 1
        self.message_user(request, f'{count} seller(s) KYC approved (ZKP not triggered).')

    # ── Register ZKP for already-approved sellers ────────────────────

    @admin.action(description='🔐 Register ZKP for approved sellers')
    def register_zkp_selected(self, request, queryset):
        count = 0
        for obj in queryset.filter(status='approved', zkp_status__in=['not_registered', 'failed']):
            _auto_register_zkp(obj, request)
            count += 1
        self.message_user(request, f'ZKP registration attempted for {count} seller(s).')

    # ── Reject ───────────────────────────────────────────────────────

    @admin.action(description='❌ Reject selected KYC submissions')
    def reject_selected(self, request, queryset):
        count = 0
        for obj in queryset.exclude(status='approved'):
            obj.mark_rejected(notes='Bulk rejected via admin.', admin_user=request.user)
            count += 1
        self.message_user(request, f'{count} seller(s) KYC rejected.')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('seller', 'reviewed_by')


# ═════════════════════════════════════════════════════════════════════════════
# SITE-LEVEL REGISTRATIONS
# ═════════════════════════════════════════════════════════════════════════════

admin.site.register(Group, GroupAdmin)
admin.site.unregister(BuiltInGroup)

admin.site.site_header = 'E-Commerce Authentication Admin'
admin.site.site_title = 'E-Commerce Admin'
admin.site.index_title = 'Welcome to E-Commerce Administration'