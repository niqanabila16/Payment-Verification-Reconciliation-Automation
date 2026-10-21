"""Teller input: one structured receipt per customer payment (DBML table "teller_submissions")."""
import uuid
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.accounts.models import Branch
from apps.core import lookups
from apps.core.models import Bank
from apps.core.normalize import normalize_reference


class SyncStatus(models.TextChoices):
    PENDING_SYNC = "pending_sync", "Pending sync"
    SYNCED = "synced", "Synced"


def submission_fingerprint(sender, holder, relationship, bank_id, amount, reference, method, transaction_at) -> str:
    """Every value a Teller can edit, normalised, so "the same data entered again" can be recognised."""
    when = ""
    if transaction_at is not None and hasattr(transaction_at, "isoformat"):
        if timezone.is_aware(transaction_at):
            transaction_at = transaction_at.astimezone(dt_timezone.utc)
        when = transaction_at.replace(second=0, microsecond=0).isoformat()
    return "|".join([" ".join((sender or "").upper().split()), " ".join((holder or "").upper().split()), relationship or "", str(bank_id or ""),
                     f"{Decimal(amount):.2f}" if amount is not None else "", normalize_reference(reference), method or "", when])


class TellerSubmission(models.Model):
    # Created in the browser when the Teller opens the form; makes offline sync idempotent.
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="submissions")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                     related_name="submissions")
    sender_name = models.CharField(max_length=150, blank=True, help_text="Who handed over the money. Often unknown.")
    account_holder_name = models.CharField(max_length=150, help_text="Owner of the bank account that was used to pay.")
    relationship = models.CharField(max_length=50, blank=True, help_text="Code from the Relationship value list.")
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name="submissions")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    bank_reference_no = models.CharField(max_length=50, blank=True, help_text="As typed by the teller.")
    reference_normalized = models.CharField(max_length=50, blank=True, db_index=True,
                                            help_text="Letters/digits only, upper case (BR-2).")
    payment_method_code = models.CharField(max_length=10, help_text="Code from the Payment method value list.")
    transaction_at = models.DateTimeField(default=timezone.now, help_text="Date and time printed on the receipt, typed by the Teller.")
    entered_at = models.DateTimeField(default=timezone.now, help_text="When the Teller typed it (may be at night, offline).")
    sync_status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.PENDING_SYNC)
    synced_at = models.DateTimeField(null=True, blank=True)
    previous_versions = models.JSONField(default=list, blank=True, help_text="Fingerprints of the values this receipt had before each correction. "
                                         "A correction that repeats any earlier version is refused with a warning (nothing was really corrected).")

    class Meta:
        ordering = ["-entered_at"]
        # Indexes follow the most frequent lookups (docs/DATABASE.md "Search analysis").
        indexes = [
            models.Index(fields=["branch", "-entered_at"], name="sub_branch_entered_idx"),   # Teller list per branch
            models.Index(fields=["reference_normalized", "amount"], name="sub_ref_amount_idx"),  # duplicate check on every save
            models.Index(fields=["bank", "-entered_at"], name="sub_bank_entered_idx"),     # Finance bank filter
            models.Index(fields=["transaction_at"], name="sub_txn_at_idx"),               # report periods
        ]

    @property
    def fingerprint(self) -> str:
        return submission_fingerprint(self.sender_name, self.account_holder_name, self.relationship, self.bank_id, self.amount,
                                      self.bank_reference_no, self.payment_method_code, self.transaction_at)

    @property
    def payment_method_label(self) -> str:
        return lookups.label("payment_method", self.payment_method_code)

    @property
    def relationship_label(self) -> str:
        return lookups.label("relationship", self.relationship)

    def save(self, *args, **kwargs):
        self.reference_normalized = normalize_reference(self.bank_reference_no)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"#{self.pk} {self.sender_name} RM {self.amount} ({self.bank_reference_no})"
