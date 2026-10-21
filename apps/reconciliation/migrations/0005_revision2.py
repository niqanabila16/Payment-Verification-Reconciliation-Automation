"""
Revision 2: only the extracted bank columns are stored, rows of non-reconciled types are kept as Open Items,
a receipt can be Rejected (Teller sees "Reject"), Review carries its reasons, verified matches keep a snapshot of the bank row.
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def convert_statuses(apps, schema_editor):
    Match = apps.get_model("reconciliation", "ReconciliationMatch")
    # "Review: typo" suggestions no longer exist: those receipts go back to Pending and are matched again on the next upload.
    Match.objects.filter(match_status="typo").update(match_status="pending", suggested_bank_statement_entry=None, match_type="",
                                                     match_score=None, notes="")
    Match.objects.filter(match_status="manual_review").update(review_reasons=["amount"])
    # Verified matches keep a copy of their bank row (the bank data is purged after 31 days).
    for match in Match.objects.filter(match_status="gfp").exclude(bank_statement_entry=None).select_related("bank_statement_entry", "bank_statement_entry__statement_import"):
        entry = match.bank_statement_entry
        when = entry.transaction_date or entry.statement_import.statement_date
        match.bank_snapshot = {"name": entry.counterparty_name, "amount": str(entry.amount), "reference": entry.reference,
                               "reference_normalized": entry.reference_normalized, "description": entry.description,
                               "direction": "Credit" if entry.credit_amount else "Debit", "date": when.isoformat() if when else "",
                               "source_row": entry.source_row, "file": entry.statement_import.file_name}
        match.save(update_fields=["bank_snapshot"])


def strip_ref_apostrophe(apps, schema_editor):
    """RHB prints Bank Ref No. as text with a leading apostrophe; the new reader drops it, so old rows are cleaned the same way."""
    Entry = apps.get_model("reconciliation", "StatementEntry")
    for entry in Entry.objects.filter(bank_ref_no__startswith="'").iterator():
        clean = entry.bank_ref_no.lstrip("'")
        if clean and not Entry.objects.filter(statement_import__bank_id=entry.statement_import.bank_id, bank_ref_no=clean).exists():
            Entry.objects.filter(pk=entry.pk).update(bank_ref_no=clean)


class Migration(migrations.Migration):

    dependencies = [
        ("reconciliation", "0004_alter_reconciliationmatch_options_and_more"),
    ]

    operations = [
        # ---- statement rows: only the extracted columns
        migrations.RenameField("statemententry", "reference_1", "reference"),
        migrations.RemoveField("statemententry", "reference_2"),
        migrations.RemoveField("statemententry", "references"),
        migrations.RemoveField("statemententry", "raw_columns"),
        migrations.RemoveField("statemententry", "bank_branch_code"),
        migrations.AddField("statemententry", "matchable", models.BooleanField(
            default=True, help_text="False: a transaction type that is not reconciled (it is an Open Item straight away, for reports).")),
        migrations.AlterField("statemententry", "reference", models.CharField(
            blank=True, max_length=150, help_text="Reference used for matching, e.g. QR85237862, RPP260829309437120, 0000006932.")),
        migrations.AlterField("statemententry", "bank_ref_no", models.CharField(
            max_length=50, help_text="Unique key of the row inside the bank/account (duplicate protection).")),
        migrations.AlterField("statemententry", "description", models.CharField(
            blank=True, max_length=100, help_text="Transaction description of the bank (spaces squeezed).")),
        migrations.AlterField("statemententry", "counterparty_name", models.CharField(
            blank=True, max_length=150, help_text="Name used for matching: compared with the Teller's ACCOUNT HOLDER.")),
        migrations.AlterField("statementimport", "imported_at", models.DateTimeField(
            db_index=True, default=django.utils.timezone.now,
            help_text="Bank data is deleted BANK_DATA_RETENTION_DAYS (31) days after this moment.")),
        # ---- matches
        migrations.AddField("reconciliationmatch", "review_reasons", models.JSONField(
            blank=True, default=list, help_text="Which fields differ in Review: any of name, amount, reference (revision 2: only amount).")),
        migrations.AddField("reconciliationmatch", "bank_snapshot", models.JSONField(
            blank=True, default=dict, help_text="Values of the bank row at the moment of GFP.")),
        migrations.AddField("reconciliationmatch", "rejected_bank_statement_entry", models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rejected_for",
            to="reconciliation.statemententry", help_text="The bank row Finance compared and rejected. Kept so the detail page still shows the one comparison.")),
        migrations.RemoveField("reconciliationmatch", "rejected_entry_ids"),
        migrations.AlterField("reconciliationmatch", "bank_statement_entry", models.OneToOneField(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="match", to="reconciliation.statemententry",
            help_text="Only set once the match is FINAL (verified). Becomes empty when the bank data is purged; bank_snapshot keeps the values.")),
        migrations.AlterField("reconciliationmatch", "match_status", models.CharField(
            choices=[("pending", "Pending"), ("gfp", "Verified (GFP)"), ("not_found", "Not found"), ("manual_review", "Review"), ("rejected", "Reject")],
            db_index=True, default="pending", max_length=20)),
        migrations.AlterField("reconciliationmatch", "suggested_bank_statement_entry", models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="suggested_for", to="reconciliation.statemententry",
            help_text="Machine suggestion waiting for Finance confirmation (Review).")),
        migrations.AlterField("reconciliationmatch", "finance_note", models.TextField(
            blank=True, help_text="The single Note field Finance fills when approving (GFP) or rejecting.")),
        migrations.RunPython(convert_statuses, migrations.RunPython.noop),
        migrations.RunPython(strip_ref_apostrophe, migrations.RunPython.noop),
    ]
