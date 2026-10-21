"""
Creates demo USERS only (Admin, Finance, two Customer service accounts with different rights, two Tellers) plus the 8 branches.
No receipts and no bank rows are created: enter receipts as a Teller and upload the sample statement as Finance.

    python manage.py seed_demo            # safe to run twice
    python manage.py seed_demo --reset    # delete users and all receipts/statements first (development only!)
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.accounts.models import Branch, CsPerm, Role, User
from apps.core.models import Notification
from apps.cards.models import ActivationRequest, Card, CardUpload
from apps.reconciliation.models import ReconciliationMatch, StatementEntry, StatementImport
from apps.receipts.models import TellerSubmission

DEMO_PASSWORD = "mandiri123"
BRANCHES = [("SA", "Shah Alam"), ("SN", "Senai"), ("PR", "Prai"), ("KJ", "Kajang"), ("JI", "Jalan Ipoh"), ("IP", "Ipoh"), ("BJ", "Bukit Jambul"), ("AP", "Ampang")]
USERS = [
    ("Ana Admin", "admin@demo.test", Role.ADMIN, None),
    ("Farid Finance", "finance@demo.test", Role.FINANCE, None),
    ("Citra Customer Service (A: activation only)", "cs@demo.test", Role.CS, None),
    ("Bagas Customer Service (B: activation + block)", "cs.b@demo.test", Role.CS, None),
    ("Tina Teller", "teller.kj@demo.test", Role.TELLER, "KJ"),
    ("Putra Teller", "teller.sa@demo.test", Role.TELLER, "SA"),
]
CS_RIGHTS = {"cs@demo.test": CsPerm.BATCH | CsPerm.ACTIVATION, "cs.b@demo.test": CsPerm.BATCH | CsPerm.ACTIVATION | CsPerm.BLOCK}


class Command(BaseCommand):
    help = "Create demo users (and their branches). No fake receipts."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete users, receipts and statements first (development only).")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            ReconciliationMatch.objects.all().delete()
            StatementEntry.objects.all().delete()
            StatementImport.objects.all().delete()
            TellerSubmission.objects.all().delete()
            ActivationRequest.objects.all().delete()
            Card.objects.all().delete()
            CardUpload.objects.all().delete()
            Notification.objects.all().delete()
            # The audit log refuses bulk deletes by design; a development reset is the only place we bypass it.
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM core_auditlog")
            User.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing data deleted."))

        for code, name in BRANCHES:
            Branch.objects.get_or_create(code=code, defaults={"name": name})
        for name, email, role, branch_code in USERS:
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(email=email, password=DEMO_PASSWORD, name=name, role=role,
                                         branch=Branch.objects.get(code=branch_code) if branch_code else None,
                                         **({"cs_permissions": CS_RIGHTS[email]} if email in CS_RIGHTS else {}))

        self.stdout.write(self.style.SUCCESS("Demo users ready. Password for all: " + DEMO_PASSWORD))
        for _, email, role, _ in USERS:
            self.stdout.write(f"  {role:8} {email}")
