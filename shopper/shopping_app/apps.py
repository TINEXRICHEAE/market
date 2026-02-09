from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ShoppingAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = 'shopping_app'  # Updated to include the full path
    label = 'shopping_app'      # Added label

    def ready(self):
        from . import signals  # Import the signals module

        # Connect the post_migrate signal to create the anonymous user
        post_migrate.connect(signals.create_anonymous_user, sender=self)
