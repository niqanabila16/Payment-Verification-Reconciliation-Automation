from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_delete_passwordresetrequest"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(choices=[("teller", "Teller"), ("finance", "Finance"), ("admin", "Admin"), ("cs", "Customer service")], max_length=10),
        ),
        migrations.AlterField(
            model_name="user",
            name="branch",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.deletion.PROTECT, related_name="users", to="accounts.branch",
                help_text="Required for tellers; empty for Finance, Customer service and Admin."),
        ),
    ]
