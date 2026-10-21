"""Admin-managed options of the "Transaction description" filter, with the descriptions of the three known banks."""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

DEFAULTS = {
    "ALB": ["DuitNow CR Trf CA", "CDM CA CSH DEP-W/O C", "IB2G CA Common Chrg"],
    "PBB": ["DUITNOW TRSF CR", "SI CR", "TSFR FUND CR-ATM/EFT", "DEP-CASH"],
    "RHB": ["DUITNOW QR POS CR", "RPP INWARD INST TRF"],
}


def seed(apps, schema_editor):
    Bank = apps.get_model("core", "Bank")
    TransactionDescription = apps.get_model("core", "TransactionDescription")
    for bank_code, names in DEFAULTS.items():
        bank = Bank.objects.filter(code=bank_code).first()
        for name in names:
            code = "".join(ch for ch in name.upper() if ch.isalnum())
            TransactionDescription.objects.get_or_create(code=code, defaults={"name": name, "bank": bank})


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_seed_bank_categories"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransactionDescription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(editable=False, help_text="Derived from the name (letters and digits only).", max_length=120, unique=True)),
                ("name", models.CharField(help_text="Description exactly as the bank statement prints it.", max_length=100)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("bank", models.ForeignKey(blank=True, help_text="Leave empty to offer this option for every bank.", null=True,
                                           on_delete=django.db.models.deletion.CASCADE, related_name="descriptions", to="core.bank")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
