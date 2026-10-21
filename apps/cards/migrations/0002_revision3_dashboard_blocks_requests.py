"""
Revision 3 of the cards app.

Storage: statuses become SMALLINT codes, the card number VARCHAR(19), the counters SMALLINT; the card table keeps ONE composite index
(status, branch) instead of two overlapping ones. New: customer data + reject type/reason + the dates the Excel report needs on a
request, the collection date on a card, and the small CardBlock table.
"""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

CARD_CODES = {"not_sent": 0, "delivered": 1, "accepted": 2}
REQUEST_CODES = {"sent": 0, "activation_requested": 1, "activated": 2, "rejected": 3}


def codes_forward(apps, schema_editor):
    Card = apps.get_model("cards", "Card")
    Request = apps.get_model("cards", "ActivationRequest")
    too_long = Card.objects.extra(where=["length(card_no) > 19"]).count()
    if too_long:
        raise RuntimeError(f"{too_long} stored card number(s) are longer than 19 characters; fix them before migrating.")
    for text, code in CARD_CODES.items():
        Card.objects.filter(status=text).update(status_int=code)
    for text, code in REQUEST_CODES.items():
        Request.objects.filter(status=text).update(status_int=code)
    # Requests rejected before revision 3 keep the old behaviour: the Teller can correct and send them again ("Incomplete Data").
    Request.objects.filter(status_int=3).update(follow_up=1)
    # The only moment we know for sure: the last status change of a request that is still "Activation Requested" / was "Activated".
    Request.objects.filter(status_int=1).update(mabes_at=models.F("status_changed_at"))
    Request.objects.filter(status_int=2).update(activated_at=models.F("status_changed_at"))


def codes_backward(apps, schema_editor):
    Card = apps.get_model("cards", "Card")
    Request = apps.get_model("cards", "ActivationRequest")
    for text, code in CARD_CODES.items():
        Card.objects.filter(status_int=code).update(status=text)
    Card.objects.filter(status_int__gte=3).update(status="accepted")     # collected / blocked did not exist before
    for text, code in REQUEST_CODES.items():
        Request.objects.filter(status_int=code).update(status=text)


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0001_initial"),
        ("accounts", "0005_user_cs_permissions"),
    ]

    operations = [
        # ---- new columns --------------------------------------------------------------------------------------------
        migrations.AddField("card", "status_int", models.PositiveSmallIntegerField(default=0)),
        migrations.AddField("card", "collected_at", models.DateTimeField(null=True, blank=True, help_text="Customer Collection Date: when a Teller gave the card to a customer.")),
        migrations.AddField("activationrequest", "status_int", models.PositiveSmallIntegerField(default=0)),
        migrations.AddField("activationrequest", "card", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="request", to="cards.card", help_text="The card given to the customer. Empty only for requests made before revision 3.")),
        migrations.AddField("activationrequest", "customer_name", models.CharField(blank=True, max_length=100)),
        migrations.AddField("activationrequest", "account_no", models.CharField(blank=True, max_length=20)),
        migrations.AddField("activationrequest", "id_no", models.CharField(blank=True, max_length=20)),
        migrations.AddField("activationrequest", "phone", models.CharField(blank=True, max_length=20)),
        migrations.AddField("activationrequest", "reason", models.PositiveSmallIntegerField(blank=True, null=True, choices=[(1, "Terbit Kartu Baru"), (2, "Ganti Kartu"), (3, "Kad Expired")])),
        migrations.AddField("activationrequest", "follow_up", models.PositiveSmallIntegerField(blank=True, null=True, choices=[(1, "Incomplete Data"), (2, "Return"), (3, "Close")])),
        migrations.AddField("activationrequest", "reject_reason", models.PositiveSmallIntegerField(blank=True, null=True, choices=[(1, "Nama Ibu Kandung"), (2, "Tanda Tangan Berbeda"), (3, "TTL Berbeda"), (4, "KTP Tidak Sesuai DUKCAPIL")])),
        migrations.AddField("activationrequest", "mabes_at", models.DateTimeField(blank=True, null=True, help_text="When CS recorded Activation Requested (Date Submit to Mabes).")),
        migrations.AddField("activationrequest", "activated_at", models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(codes_forward, codes_backward),
        # ---- swap the text status for the code ----------------------------------------------------------------------
        migrations.RemoveIndex("card", name="card_branch_status_idx"),
        migrations.RemoveField("card", "status"),
        migrations.RenameField("card", "status_int", "status"),
        migrations.AlterField("card", "status", models.PositiveSmallIntegerField(choices=[(0, "Not Sent"), (1, "Delivered"), (2, "Accepted"), (3, "Collected"), (4, "Blocked")], default=0)),
        migrations.AddIndex("card", models.Index(fields=["status", "branch"], name="card_status_branch_idx")),
        migrations.RemoveField("activationrequest", "status"),
        migrations.RenameField("activationrequest", "status_int", "status"),
        migrations.AlterField("activationrequest", "status", models.PositiveSmallIntegerField(choices=[(0, "Sent"), (1, "Activation Requested"), (2, "Card Activated"), (3, "Reject")], db_index=True, default=0)),
        # ---- narrower types ------------------------------------------------------------------------------------------
        migrations.AlterField("card", "card_no", models.CharField(max_length=19, unique=True)),
        migrations.AlterField("activationrequest", "resubmit_count", models.PositiveSmallIntegerField(default=0)),
        migrations.AlterField("activationrequest", "file_name", models.CharField(max_length=255, help_text="Original file name of the customer's PDF.")),
        migrations.AlterField("activationrequest", "cs_note", models.TextField(blank=True, help_text="Legacy free-text note of requests rejected before revision 3. Not used any more.")),
        # ---- blocked cards -------------------------------------------------------------------------------------------
        migrations.CreateModel(
            name="CardBlock",
            fields=[
                ("card", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="block", serialize=False, to="cards.card")),
                ("note", models.CharField(max_length=255)),
                ("blocked_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("blocked_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
