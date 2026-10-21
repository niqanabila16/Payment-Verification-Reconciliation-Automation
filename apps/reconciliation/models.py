"""
Reconciliation data model (DBML tables bank_statement_imports, bank_statement_entries,
reconciliation_matches).

A bank statement row stores ONLY what the matching uses (revision 2): the name (account holder), the amount (debit or
credit), the reference and the transaction description / date. Every other column of the bank file is ignored.
"""
from types import SimpleNamespace

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Bank
from apps.receipts.models import TellerSubmission


class StatementFormat(models.TextChoices):
    CSV = "csv", "CSV"
    XLSX = "xlsx", "XLSX"


class ImportStatus(models.TextChoices):
    PROCESSING = "processing", "Processing"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"


class StatementImport(models.Model):
    """One uploaded bank statement file."""

    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name="imports")
    account_number = models.CharField(max_length=30)
    account_label = models.CharField(max_length=100, blank=True)
    statement_date = models.DateField(help_text='"as at" date from the statement header.')
    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64, db_index=True, help_text="Used to warn when the same file is uploaded again.")
    file_format = models.CharField(max_length=10, choices=StatementFormat.choices, default=StatementFormat.CSV)
    row_count = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.PROCESSING)
    imported_at = models.DateTimeField(default=timezone.now, db_index=True, help_text="Bank data is deleted BANK_DATA_RETENTION_DAYS (31) days after this moment.")
    # (added)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="imports")
    progress_percent = models.PositiveSmallIntegerField(default=0)
    error_message = models.TextField(blank=True)
    result_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-imported_at"]

    def __str__(self) -> str:
        return f"{self.file_name} ({self.statement_date})"


class StatementEntry(models.Model):
    """One transaction row of a bank statement (only the extracted columns)."""

    statement_import = models.ForeignKey(StatementImport, on_delete=models.CASCADE, related_name="entries")
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name="entries", help_text="Copied from the import so rows can be filtered by bank without a join.")
    description = models.CharField(max_length=100, blank=True, help_text="Transaction description of the bank (spaces squeezed).")
    debit_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                                 help_text="The value of whichever of Debit / Credit is filled (a row has only one). Matching uses this.")
    transaction_date = models.DateField(null=True, blank=True, help_text="Date column of the bank file, when the bank provides one.")
    counterparty_name = models.CharField(max_length=150, blank=True, help_text="Name used for matching: compared with the Teller's ACCOUNT HOLDER.")
    reference = models.CharField(max_length=150, blank=True, help_text="Reference used for matching, e.g. QR85237862, RPP260829309437120, 0000006932.")
    bank_ref_no = models.CharField(max_length=50, help_text="Unique key of the row inside the bank/account (duplicate protection).")
    reference_normalized = models.CharField(max_length=150, blank=True, db_index=True)
    matchable = models.BooleanField(default=True, help_text="False: a transaction type that is not reconciled (it is an Open Item straight away, for reports).")
    # (added) row number in the uploaded file, to point Finance at the exact line
    source_row = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["statement_import_id", "source_row", "id"]
        constraints = [
            models.UniqueConstraint(fields=["statement_import", "bank_ref_no"], name="uniq_ref_per_import"),
        ]
        indexes = [
            models.Index(fields=["bank", "amount"], name="entry_bank_amount_idx"),   # matching: same bank + same amount
            models.Index(fields=["bank_ref_no"], name="entry_bankref_idx"),         # re-upload / overlap check
            models.Index(fields=["transaction_date"], name="entry_txn_date_idx"),   # report periods
        ]

    def __str__(self) -> str:
        return f"{self.bank_ref_no} {self.amount}"

    @property
    def direction(self) -> str:
        return "Credit" if self.credit_amount else "Debit"

    @property
    def display_reference(self) -> str:
        return self.reference or ""

    @property
    def display_date(self):
        return self.transaction_date or self.statement_import.statement_date

    def snapshot(self) -> dict:
        """What a verified receipt keeps of its bank row, so the comparison stays readable after the bank data is purged."""
        return {"name": self.counterparty_name, "amount": str(self.amount), "reference": self.reference,
                "reference_normalized": self.reference_normalized, "description": self.description, "direction": self.direction,
                "date": self.display_date.isoformat() if self.display_date else "", "source_row": self.source_row,
                "file": self.statement_import.file_name if self.statement_import_id else ""}


def entry_from_snapshot(data: dict):
    """A read-only stand-in for a purged StatementEntry, with the attributes the comparison screen uses."""
    from datetime import date
    from decimal import Decimal

    when = None
    try:
        when = date.fromisoformat(data.get("date") or "")
    except ValueError:
        pass
    return SimpleNamespace(
        counterparty_name=data.get("name", ""), amount=Decimal(data.get("amount") or 0), reference=data.get("reference", ""),
        reference_normalized=data.get("reference_normalized", ""), display_reference=data.get("reference", ""), description=data.get("description", ""),
        direction=data.get("direction", ""), display_date=when, source_row=data.get("source_row"), is_snapshot=True,
        file_name=data.get("file", ""))


class MatchType(models.TextChoices):
    AUTO_EXACT = "auto_exact", "Automatic (exact)"
    AUTO_FUZZY = "auto_fuzzy", "Automatic (fuzzy)"   # not produced any more (typo suggestions were removed in revision 2); kept for old rows
    MANUAL = "manual", "Manual"


class MatchStatus(models.TextChoices):
    """
    Statuses use the business vocabulary of the Finance team.
    Tellers see three of them: Pending (everything not decided yet), Verified (GFP) and Reject.
    """

    PENDING = "pending", "Pending"
    GFP = "gfp", "Verified (GFP)"
    NOT_FOUND = "not_found", "Not found"
    MANUAL_REVIEW = "manual_review", "Review"
    REJECTED = "rejected", "Reject"


class ReviewReason(models.TextChoices):
    """Why a receipt is in Review: which of the three matching fields (name, amount, reference) does not match."""

    NAME = "name", "name differs"
    AMOUNT = "amount", "amount differs"
    REFERENCE = "reference", "reference differs"


OPEN_STATUSES = (MatchStatus.PENDING, MatchStatus.NOT_FOUND, MatchStatus.MANUAL_REVIEW, MatchStatus.REJECTED)
REVIEW_STATUSES = (MatchStatus.MANUAL_REVIEW,)


class ReconciliationMatch(models.Model):
    """The reconciliation result for exactly one Teller submission (BR-6: never left hanging)."""

    teller_submission = models.OneToOneField(TellerSubmission, on_delete=models.CASCADE, related_name="match")
    bank_statement_entry = models.OneToOneField(
        StatementEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="match",
        help_text="Only set once the match is FINAL (verified). Becomes empty when the bank data is purged; bank_snapshot keeps the values.",
    )
    suggested_bank_statement_entry = models.ForeignKey(
        StatementEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="suggested_for",
        help_text="Machine suggestion waiting for Finance confirmation (Review).",
    )
    rejected_bank_statement_entry = models.ForeignKey(
        StatementEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="rejected_for",
        help_text="The bank row Finance compared and rejected. Kept so the detail page still shows the one comparison.",
    )
    bank_snapshot = models.JSONField(default=dict, blank=True, help_text="Values of the bank row at the moment of GFP.")
    review_reasons = models.JSONField(default=list, blank=True, help_text="Which fields differ in Review: any of name, amount, reference (revision 2: only amount).")
    match_type = models.CharField(max_length=20, choices=MatchType.choices, blank=True)
    match_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    match_status = models.CharField(max_length=20, choices=MatchStatus.choices, default=MatchStatus.PENDING, db_index=True)
    first_seen_at = models.DateTimeField(default=timezone.now, help_text="When the receipt entered the queue.")
    status_changed_at = models.DateTimeField(default=timezone.now, help_text="Last time the receipt arrived or its status changed. The Finance table is sorted newest first by this.")
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    matched_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", help_text="Empty for automatic matches.")
    matched_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Engine explanation shown on the detail page.")
    finance_note = models.TextField(blank=True, help_text="The single Note field Finance fills when approving (GFP) or rejecting.")

    class Meta:
        ordering = ["-status_changed_at", "-id"]  # newest arrival / newest match first
        indexes = [
            models.Index(fields=["match_status", "-status_changed_at"], name="match_status_recent_idx"),  # every Finance tab
        ]

    def __str__(self) -> str:
        return f"match #{self.pk} {self.match_status}"

    @property
    def is_open(self) -> bool:
        return self.match_status != MatchStatus.GFP

    @property
    def teller_status(self) -> str:
        """Tellers see Pending, Verified or Reject; every other unresolved state is "pending" for them."""
        if self.match_status in (MatchStatus.GFP, MatchStatus.REJECTED):
            return self.match_status
        return MatchStatus.PENDING

    @property
    def review_label(self) -> str:
        """"Review: amount differs" (the reasons come from review_reasons)."""
        names = {r.value: r.label for r in ReviewReason}
        reasons = [names[r] for r in (self.review_reasons or []) if r in names]
        return "Review: " + " and ".join(reasons) if reasons else "Review"
