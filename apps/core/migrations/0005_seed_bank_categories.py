"""
Bank categories: RHB, ALB, PBB and MBB, each with its statement reader.
Older databases: an existing RHB / PBB bank gets its reader, MAYBANK becomes MBB, and the placeholder bank MANDIRI
(used by the previous version) is removed when nothing refers to it.
"""
from django.db import migrations

BANKS = [("RHB", "RHB Bank", "rhb"), ("ALB", "Alliance Bank", "alb"), ("PBB", "Public Bank", "pbb"), ("MBB", "Maybank", "mbb")]


def seed(apps, schema_editor):
    Bank = apps.get_model("core", "Bank")
    Submission = apps.get_model("receipts", "TellerSubmission")
    Import = apps.get_model("reconciliation", "StatementImport")
    if not Bank.objects.filter(code="MBB").exists():
        Bank.objects.filter(code="MAYBANK").update(code="MBB")
    for code, name, fmt in BANKS:
        bank, _ = Bank.objects.get_or_create(code=code, defaults={"name": name, "statement_format": fmt})
        if not bank.statement_format:
            bank.statement_format = fmt
            bank.save(update_fields=["statement_format"])
    mandiri = Bank.objects.filter(code="MANDIRI").first()
    if mandiri and not Submission.objects.filter(bank=mandiri).exists() and not Import.objects.filter(bank=mandiri).exists():
        mandiri.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_bank_statement_format"),
        ("receipts", "0003_rename_receipts_te_branch__d1bbbd_idx_sub_branch_entered_idx_and_more"),
        ("reconciliation", "0004_alter_reconciliationmatch_options_and_more"),
    ]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
