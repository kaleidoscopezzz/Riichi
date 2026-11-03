from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Local identity only. External identities belong to a future separate module."""
