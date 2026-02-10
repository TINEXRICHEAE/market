from django.contrib import admin
from django.contrib.auth.models import Group as BuiltInGroup
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin
from django.contrib.auth.models import Permission
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
    Wishlist, Order, OrderItem
)


class GroupAdmin(GuardedModelAdmin, BaseGroupAdmin):
    """Enhanced Group Admin with better organization and permissions"""
    list_display = ('name', 'admin_display', 'superadmin_display',
                    'member_count', 'permission_count')
    search_fields = ('name', 'admin__email', 'superadmin__email')
    list_filter = ('admin__role', 'superadmin__role')
    filter_horizontal = ('permissions',)
    ordering = ('name',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('name',)
        }),
        ('Management', {
            'fields': ('admin', 'superadmin'),
            'description': 'Assign administrators for this group'
        }),
        ('Permissions', {
            'fields': ('permissions',),
            'classes': ('collapse',),
            'description': 'Specific permissions for this group'
        }),
    )

    def admin_display(self, obj):
        if obj.admin:
            return format_html(
                '<span style="color: #0066cc;"><strong>{}</strong></span>',
                obj.admin.email
            )
        return format_html('<span style="color: #999;">No admin assigned</span>')
    admin_display.short_description = 'Admin'

    def superadmin_display(self, obj):
        if obj.superadmin:
            return format_html(
                '<span style="color: #cc0000;"><strong>{}</strong></span>',
                obj.superadmin.email
            )
        return format_html('<span style="color: #999;">No superadmin assigned</span>')
    superadmin_display.short_description = 'Super Admin'

    def member_count(self, obj):
        count = obj.user_set.count()
        return format_html('<span class="badge">{}</span>', count)
    member_count.short_description = 'Members'

    def permission_count(self, obj):
        count = obj.permissions.count()
        return format_html('<span class="badge">{}</span>', count)
    permission_count.short_description = 'Permissions'

    def has_module_permission(self, request):
        if super().has_module_permission(request):
            return True
        return self.get_model_objects(request).exists()

    def get_queryset(self, request):
        if request.user.is_superuser:
            return super().get_queryset(request).select_related('admin', 'superadmin')
        data = self.get_model_objects(request)
        return data.select_related('admin', 'superadmin')

    def get_model_objects(self, request, action=None, klass=None):
        opts = self.opts
        actions = [action] if action else ['view', 'change', 'delete']
        klass = klass if klass else opts.model
        model_name = klass._meta.model_name
        return get_objects_for_user(
            user=request.user,
            perms=[f'{opts.app_label}.{perm}_{model_name}' for perm in actions],
            klass=klass,
            any_perm=True
        )

    def has_permission(self, request, obj, action):
        opts = self.opts
        code_name = f'{action}_{opts.model_name}'
        if obj:
            return request.user.has_perm(f'{opts.app_label}.{code_name}', obj)
        else:
            return self.get_model_objects(request).exists()

    def has_view_permission(self, request, obj=None):
        return self.has_permission(request, obj, 'view')

    def has_change_permission(self, request, obj=None):
        return self.has_permission(request, obj, 'change')

    def has_delete_permission(self, request, obj=None):
        return self.has_permission(request, obj, 'delete')


@admin.register(Users)
class UsersAdmin(GuardedModelAdmin, UserAdmin):
    """Enhanced Users Admin with comprehensive user management"""
    list_display = (
        'id', 'email', 'role_badge', 'phone_display', 'status_display',
        'last_login', 'date_joined_display'
    )
    search_fields = ('email', 'phonenumber')
    list_filter = ('role', 'is_active', 'is_staff',
                   'is_superuser', 'created_at')
    ordering = ('-created_at',)
    filter_horizontal = ('user_permissions', 'groups')

    fieldsets = (
        ('Account Information', {
            'fields': ('email', 'password'),
            'classes': ('wide',)
        }),
        ('Personal Information', {
            'fields': ('role', 'phonenumber'),
            'classes': ('wide',)
        }),
        ('Group Membership', {
            'fields': ('groups',),
            'classes': ('collapse',)
        }),
        ('Permissions & Status', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'user_permissions'),
            'classes': ('collapse',),
            'description': 'Detailed permissions and account status'
        }),
        ('Important Dates', {
            'fields': ('last_login', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        ('Create New User', {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role', 'phonenumber', 'groups'),
            'description': 'Enter the user information below'
        }),
        ('Permissions (Optional)', {
            'classes': ('collapse',),
            'fields': ('user_permissions',),
        }),
    )

    readonly_fields = ('created_at', 'updated_at', 'last_login')

    def role_badge(self, obj):
        colors = {
            'buyer': '#28a745',
            'seller': '#17a2b8',
            'admin': '#ffc107',
            'superadmin': '#dc3545'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.role, '#6c757d'),
            obj.get_role_display()
        )
    role_badge.short_description = 'Role'

    def phone_display(self, obj):
        if obj.phonenumber:
            return format_html('<span style="font-family: monospace;">{}</span>', obj.phonenumber)
        return format_html('<span style="color: #999;">Not provided</span>')
    phone_display.short_description = 'Phone'

    def status_display(self, obj):
        if obj.is_active:
            if obj.is_superuser:
                return format_html('<span style="color: #dc3545;">●</span> Super User')
            elif obj.is_staff:
                return format_html('<span style="color: #ffc107;">●</span> Staff')
            else:
                return format_html('<span style="color: #28a745;">●</span> Active')
        return format_html('<span style="color: #6c757d;">●</span> Inactive')
    status_display.short_description = 'Status'

    def date_joined_display(self, obj):
        return obj.created_at.strftime('%b %d, %Y')
    date_joined_display.short_description = 'Date Joined'

    def save_model(self, request, obj, form, change):
        if not change:  # Only during creation
            if obj.role == 'admin':
                obj.is_staff = True
                obj.is_superuser = False
            elif obj.role == 'superadmin':
                obj.is_staff = True
                obj.is_superuser = True
            else:
                obj.is_staff = False
                obj.is_superuser = False
            obj.is_active = True

        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        is_superuser = request.user.is_superuser

        if not is_superuser:
            form.base_fields['role'].disabled = True
            form.base_fields['is_superuser'].disabled = True
            form.base_fields['user_permissions'].disabled = True
            form.base_fields['groups'].disabled = True
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.exclude(email="anonymous@example.com").prefetch_related('groups')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at')
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'category', 'price',
                    'stock_quantity', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'seller')
    search_fields = ('name', 'description')
    list_editable = ('price', 'stock_quantity', 'is_active')
    ordering = ('-created_at',)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('added_at',)


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


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('subtotal',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'buyer',
                    'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'buyer__email')
    readonly_fields = ('order_number', 'created_at', 'updated_at')
    inlines = [OrderItemInline]



# Register models with enhanced admin
admin.site.register(Group, GroupAdmin)
admin.site.unregister(BuiltInGroup)

# Customize admin site header and title
admin.site.site_header = 'E-Commerce Authentication Admin'
admin.site.site_title = 'E-Commerce Admin'
admin.site.index_title = 'Welcome to E-Commerce Administration'
