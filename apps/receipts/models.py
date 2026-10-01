"""Teller input: one structured receipt per customer payment (DBML table "teller_submissions")."""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import Branch
from apps.core.models import Bank
from apps.core.normalize import normalize_reference

from .constants import PAYMENT_METHODS, RELATIONSHIPS


class SyncStatus(models.TextChoices):
    PENDING_SYNC = "pending_sync", "Pending sync"
    SYNCED = "synced", "Synced"


class TellerSubmission(models.Model):
    # Created in the browser when the Teller opens the form; makes offline sync idempotent.
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="submissions")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                     related_name="submissions")
    sender_name = models.CharField(max_length=150)
    account_holder_name = models.CharField(max_length=150, help_text="Name on the bank account used to pay.")
    relationship = models.CharField(max_length=50, choices=RELATIONSHIPS, blank=True)
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name="submissions")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    bank_reference_no = models.CharField(max_length=50, blank=True, help_text="As typed by the teller.")
    reference_normalized = models.CharField(max_length=50, blank=True, db_index=True,
                                            help_text="Letters/digits only, upper case (BR-2).")
    payment_method_code = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    entered_at = models.DateTimeField(default=timezone.now, help_text="When the Teller typed it (may be at night, offline).")
    sync_status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING_SYNC)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-entered_at"]
        indexes = [models.Index(fields=["branch", "-entered_at"])]

    def save(self, *args, **kwargs):
        self.reference_normalized = normalize_reference(self.bank_reference_no)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"#{self.pk} {self.sender_name} RM {self.amount} ({self.bank_reference_no})"
