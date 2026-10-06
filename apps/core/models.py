"""Shared master data (banks), the append-only audit trail and user notifications."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Bank(models.Model):
    """A bank used for deposits / statements (master data)."""

    code = models.CharField(max_length=20, unique=True, help_text="e.g. RHB, MANDIRI")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, help_text="Inactive banks are hidden from dropdowns; history is kept.")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PaymentMethod(models.Model):
    """Value list for the Teller form dropdown "Payment method". Managed by Admin."""

    code = models.CharField(max_length=10, unique=True, help_text="Stored on receipts, e.g. CASH.")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Relationship(models.Model):
    """Value list for the Teller form dropdown "Relationship to sender". Managed by Admin."""

    code = models.CharField(max_length=50, unique=True, help_text="Stored on receipts, e.g. SIBLING.")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AuditLogQuerySet(models.QuerySet):
    """Blocks bulk UPDATE / DELETE so the trail cannot be rewritten (NFR-010)."""

    def update(self, **kwargs):
        raise PermissionError("Audit log entries are append-only.")

    def delete(self):
        raise PermissionError("Audit log entries are append-only.")


class AuditLog(models.Model):
    """Who did what to which record. Rows are only ever inserted."""

    entity_type = models.CharField(max_length=50)
    entity_id = models.BigIntegerField()
    action = models.CharField(max_length=50)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Audit log entries are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit log entries are append-only.")

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}#{self.entity_id}"


class Notification(models.Model):
    """In-app notification (also surfaced as a browser notification, BR-7)."""

    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-app"
        EMAIL = "email", "E-mail"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    recipient_role = models.CharField(max_length=10, blank=True, help_text="Broadcast to a whole role.")
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.IN_APP)
    type = models.CharField(max_length=50)
    related_entity_type = models.CharField(max_length=50, blank=True)
    related_entity_id = models.BigIntegerField(null=True, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, default="unread")
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "status"])]

    @property
    def is_unread(self) -> bool:
        return self.status == "unread"
