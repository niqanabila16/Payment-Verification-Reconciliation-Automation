"""Data step before the schema change: the "Closed" status is removed, so closed items become "Not found" again."""
from django.db import migrations


def closed_to_not_found(apps, schema_editor):
    Match = apps.get_model("reconciliation", "ReconciliationMatch")
    Match.objects.filter(match_status="closed").update(match_status="not_found")


class Migration(migrations.Migration):
    dependencies = [("reconciliation", "0001_initial")]
    operations = [migrations.RunPython(closed_to_not_found, migrations.RunPython.noop)]
