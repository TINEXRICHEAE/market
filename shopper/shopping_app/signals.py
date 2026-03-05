import logging
import requests

from django.conf import settings
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import Permission
from .models import Users, Group

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Existing: assign user to group on creation
# ─────────────────────────────────────────────────────────────────────────────

@receiver(post_save, sender=Users)
def assign_user_to_group(sender, instance, created, **kwargs):
    if created:  # Only trigger for new users
        if instance.role == 'admin':
            superadmin = Users.objects.filter(role='superadmin').first()
            if superadmin:
                group, created = Group.objects.get_or_create(
                    name='Admins',
                    superadmin=superadmin
                )
                instance.groups.add(group)
                permissions = Permission.objects.filter(id__in=[24, 28, 32, 36])
                group.permissions.add(*permissions)

        elif instance.role == 'seller':
            superadmin = Users.objects.filter(role='superadmin').first()
            if superadmin:
                group, created = Group.objects.get_or_create(
                    name='Sellers',
                    superadmin=superadmin
                )
                instance.groups.add(group)

        elif instance.role == 'buyer':
            superadmin = Users.objects.filter(role='superadmin').first()
            if superadmin:
                group, created = Group.objects.get_or_create(
                    name='Buyers',
                    superadmin=superadmin
                )
                instance.groups.add(group)


def create_anonymous_user(sender, **kwargs):
    Users.objects.create_anonymous_user()

