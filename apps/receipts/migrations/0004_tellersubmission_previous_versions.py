from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("receipts", "0003_rename_receipts_te_branch__d1bbbd_idx_sub_branch_entered_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tellersubmission",
            name="previous_versions",
            field=models.JSONField(
                blank=True, default=list,
                help_text="Fingerprints of the values this receipt had before each correction. A correction that repeats any earlier version "
                          "is refused with a warning (nothing was really corrected)."),
        ),
    ]
