from django.db import migrations, models


class Migration(migrations.Migration):
    """Customer service rights as bit flags in one small integer. Existing accounts keep what they could do before (1 + 2)."""

    dependencies = [("accounts", "0004_alter_user_role")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="cs_permissions",
            field=models.PositiveSmallIntegerField(default=3, help_text="Customer service only: bit flags, see CsPerm."),
        ),
    ]
