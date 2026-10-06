"""
Reconciliation data model (DBML tables bank_statement_imports, bank_statement_entries,
reconciliation_matches, match_comments).

Columns that are NOT in DBML v4 are marked "(added)". They exist only to support the
progress bar, the upload summary and auditing.
"""
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
    statement_date = models.DateField(help_text='"as at" date from the statement header (row 1).')
    file_name = models.CharField(max_length=255)
    file_sha256 = models.CharField(max_length=64, db_index=True, help_text="Used to warn when the same file is uploaded again.")
    file_format = models.CharField(max_length=10, choices=StatementFormat.choices, default=StatementFormat.CSV)
    row_count = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ImportStatus.choices, default=ImportStatus.PROCESSING)
    imported_at = models.DateTimeField(default=timezone.now)
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
    """One transaction row of a bank statement."""

    statement_import = models.ForeignKey(StatementImport, on_delete=models.CASCADE, related_name="entries")
    description = models.CharField(max_length=100, blank=True)
    bank_branch_code = models.CharField(max_length=20, blank=True)
    debit_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    counterparty_name = models.CharField(max_length=150, blank=True)
    reference_1 = models.CharField(max_length=150, blank=True)
    reference_2 = models.CharField(max_length=150, blank=True)
    bank_ref_no = models.CharField(max_length=50)
    reference_normalized = models.CharField(max_length=150, blank=True, db_index=True)
    # (added) row number in the uploaded file, to point Finance at the exact line
    source_row = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["statement_import_id", "source_row", "id"]
        constraints = [
            models.UniqueConstraint(fields=["statement_import", "bank_ref_no"], name="uniq_ref_per_import"),
        ]

    def __str__(self) -> str:
        return f"{self.bank_ref_no} {self.credit_amount or self.debit_amount}"

    @property
    def is_credit(self) -> bool:
        return bool(self.credit_amount and self.credit_amount > 0)


class MatchType(models.TextChoices):
    AUTO_EXACT = "auto_exact", "Automatic (exact)"
    AUTO_FUZZY = "auto_fuzzy", "Automatic (fuzzy)"
    MANUAL = "manual", "Manual"


class MatchStatus(models.TextChoices):
    """
    Statuses use the business vocabulary of the Finance team.
    Tellers only ever see two of them: Pending (everything not verified yet) or Verified (GFP).
    """

    PENDING = "pending", "Pending"
    GFP = "gfp", "Verified (GFP)"
    TYPO = "typo", "Review: typo"
    NOT_FOUND = "not_found", "Not found"
    MANUAL_REVIEW = "manual_review", "Review: amount differs"


OPEN_STATUSES = (MatchStatus.PENDING, MatchStatus.TYPO, MatchStatus.NOT_FOUND, MatchStatus.MANUAL_REVIEW)
REVIEW_STATUSES = (MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW)


class ReconciliationMatch(models.Model):
    """The reconciliation result for exactly one Teller submission (BR-6: never left hanging)."""

    teller_submission = models.OneToOneField(TellerSubmission, on_delete=models.CASCADE, related_name="match")
    bank_statement_entry = models.OneToOneField(
        StatementEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="match",
        help_text="Only set once the match is FINAL (verified, or typo confirmed by Finance).",
    )
    suggested_bank_statement_entry = models.ForeignKey(
        StatementEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="suggested_for",
        help_text="Machine suggestion waiting for Finance confirmation (typo / amount difference).",
    )
    match_type = models.CharField(max_length=20, choices=MatchType.choices, blank=True)
    match_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    match_status = models.CharField(max_length=20, choices=MatchStatus.choices, default=MatchStatus.PENDING, db_index=True)
    first_seen_at = models.DateTimeField(default=timezone.now, help_text="When the receipt entered the queue (sort order).")
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    matched_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+", help_text="Empty for automatic matches.")
    matched_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Engine explanation or Finance note shown on the detail page.")

    class Meta:
        ordering = ["first_seen_at", "id"]  # oldest first (REQ-F-1.2 AC2)

    def __str__(self) -> str:
        return f"match #{self.pk} {self.match_status}"

    @property
    def is_open(self) -> bool:
        return self.match_status != MatchStatus.GFP

    @property
    def teller_status(self) -> str:
        """Tellers only see Pending or Verified; every unresolved state is "pending" for them."""
        return MatchStatus.GFP if self.match_status == MatchStatus.GFP else MatchStatus.PENDING
