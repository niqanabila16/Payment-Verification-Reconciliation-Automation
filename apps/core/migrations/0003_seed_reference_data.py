"""Starting values for the dropdowns. Admin can add, rename or deactivate them later (Master data page)."""
from django.db import migrations

PAYMENT_METHODS = [("CASH", "Cash"), ("CDM", "Cash deposit machine (CDM)"), ("TRANSFER", "Bank transfer")]
RELATIONSHIPS = [
    ("SELF", "Self (sender owns the account)"), ("SIBLING", "Sibling"), ("PARENT", "Parent"), ("SPOUSE", "Spouse"),
    ("CHILD", "Child"), ("RELATIVE", "Other relative"), ("FRIEND", "Friend"), ("EMPLOYER", "Employer"), ("OTHER", "Other"),
]


def seed(apps, schema_editor):
    PaymentMethod = apps.get_model("core", "PaymentMethod")
    Relationship = apps.get_model("core", "Relationship")
    Bank = apps.get_model("core", "Bank")
    for code, name in PAYMENT_METHODS:
        PaymentMethod.objects.get_or_create(code=code, defaults={"name": name})
    for code, name in RELATIONSHIPS:
        Relationship.objects.get_or_create(code=code, defaults={"name": name})
    # Bank statements always come from Mandiri, so this bank must exist.
    Bank.objects.get_or_create(code="MANDIRI", defaults={"name": "Bank Mandiri"})


class Migration(migrations.Migration):
    dependencies = [("core", "0002_paymentmethod_relationship_bank_is_active")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
