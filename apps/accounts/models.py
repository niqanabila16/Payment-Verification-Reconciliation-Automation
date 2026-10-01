"""Accounts: company branches and the custom User model (e-mail login, three roles)."""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class Branch(models.Model):
    """A company branch (master data). Tellers belong to exactly one branch."""

    code = models.CharField(max_length=10, unique=True, help_text="Short code, e.g. KJ.")
    name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}" if self.name else self.code


class Role(models.TextChoices):
    """The three roles defined by the SRS."""

    TELLER = "teller", "Teller"
    FINANCE = "finance", "Finance"
    ADMIN = "admin", "Admin"


class UserManager(BaseUserManager):
    """Creates users that sign in with an e-mail address instead of a username."""

    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An e-mail address is required.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", Role.TELLER)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        # Used by "manage.py createsuperuser": the first administrator account.
        extra.update(role=Role.ADMIN, is_superuser=True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Operational account (DBML table "users")."""

    name = models.CharField(max_length=150)
    email = models.EmailField(max_length=150, unique=True)
    role = models.CharField(max_length=10, choices=Role.choices)
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="users",
        help_text="Required for tellers; empty for Finance and Admin.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"

    @property
    def is_staff(self) -> bool:  # kept for Django compatibility; no Django admin site is installed
        return self.role == Role.ADMIN

    @property
    def is_teller(self) -> bool:
        return self.role == Role.TELLER

    @property
    def is_finance(self) -> bool:
        return self.role == Role.FINANCE

    @property
    def is_admin_role(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def landing_url_name(self) -> str:
        """Where this role starts after signing in."""
        return {
            Role.TELLER: "receipts:new",
            Role.FINANCE: "reconciliation:queue",
            Role.ADMIN: "accounts:user_list",
        }[self.role]
