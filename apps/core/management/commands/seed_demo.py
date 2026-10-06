"""
Creates demo USERS only (Admin, Finance, two Tellers) plus the two branches the Tellers need.
No receipts and no bank rows are created: enter receipts as a Teller and upload the sample statement as Finance.

    python manage.py seed_demo            # safe to run twice
    python manage.py seed_demo --reset    # delete users and all receipts/statements first (development only!)
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.accounts.models import Branch, Role, User
from apps.core.models import Notification
from apps.reconciliation.models import ReconciliationMatch, StatementEntry, StatementImport
from apps.receipts.models import TellerSubmission

DEMO_PASSWORD = "mandiri123"
BRANCHES = [("KJ", "Kajang"), ("PJ", "Petaling Jaya")]
USERS = [
    ("Ana Admin", "admin@demo.test", Role.ADMIN, None),
    ("Farid Finance", "finance@demo.test", Role.FINANCE, None),
    ("Tina Teller (KJ)", "teller.kj@demo.test", Role.TELLER, "KJ"),
    ("Putra Teller (PJ)", "teller.pj@demo.test", Role.TELLER, "PJ"),
]


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
                                         branch=Branch.objects.get(code=branch_code) if branch_code else None)

        self.stdout.write(self.style.SUCCESS("Demo users ready. Password for all: " + DEMO_PASSWORD))
        for _, email, role, _ in USERS:
            self.stdout.write(f"  {role:8} {email}")
