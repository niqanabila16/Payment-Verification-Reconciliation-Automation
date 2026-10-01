"""
Creates demo data so the system can be tried immediately:

    python manage.py seed_demo            # add demo data (safe to run twice)
    python manage.py seed_demo --reset    # delete everything first (development only!)

After seeding, sign in as the Finance user and upload sample_data/mandiri_statement_2026-09-30.csv.
"""
import uuid
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Branch, Role, User
from apps.core.models import Bank, Notification
from apps.reconciliation.models import MatchComment, ReconciliationMatch, StatementEntry, StatementImport
from apps.reconciliation.services.submissions import create_submission
from apps.receipts.models import TellerSubmission

DEMO_PASSWORD = "Demo-Pass-2026!"

BRANCHES = [("KJ", "Kajang"), ("PJ", "Petaling Jaya"), ("JB", "Johor Bahru")]
BANKS = [("MANDIRI", "Bank Mandiri"), ("RHB", "RHB Bank"), ("MAYBANK", "Maybank"), ("CIMB", "CIMB Bank"), ("PBB", "Public Bank")]
USERS = [
    ("Ana Admin", "admin@demo.test", Role.ADMIN, None),
    ("Farid Finance", "finance@demo.test", Role.FINANCE, None),
    ("Tina Teller (KJ)", "teller.kj@demo.test", Role.TELLER, "KJ"),
    ("Putra Teller (PJ)", "teller.pj@demo.test", Role.TELLER, "PJ"),
]
# (teller email, sender, holder, relationship, method, amount, reference) - all paid into Bank Mandiri
RECEIPTS = [
    ("teller.kj@demo.test", "MOH HAIKAL", "MOH HAIKAL", "SELF", "TRANSFER", "150.00", "2235277A1"),
    ("teller.kj@demo.test", "ALI BIN ABU", "ALI BIN ABU", "SELF", "TRANSFER", "1200.00", "611380310m"),     # lower case: BR-2
    ("teller.pj@demo.test", "NURUL HUDA", "NURUL HUDA", "SELF", "CDM", "500.00", "77881234"),
    ("teller.kj@demo.test", "TAN WEI MING", "TAN WEI MING", "SELF", "TRANSFER", "320.00", "99120054"),      # digits swapped: typo
    ("teller.pj@demo.test", "LIM AH KOW", "LIM AH KOW", "SIBLING", "TRANSFER", "205.00", "55302211"),       # amount differs: BR-8
    ("teller.kj@demo.test", "KUMAR S", "KUMAR S", "SELF", "TRANSFER", "980.00", "4400712"),
    ("teller.pj@demo.test", "DEVI A/P RAJ", "DEVI A/P RAJ", "SELF", "TRANSFER", "150.00", "8812-3456"),     # hyphen: BR-2
    ("teller.kj@demo.test", "CHONG MEI LING", "CHONG MEI LING", "SELF", "TRANSFER", "400.00", "90019001"),  # not in the bank file
]


class Command(BaseCommand):
    help = "Create demo branches, banks, users and Teller receipts."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete all data first (development only).")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            MatchComment.objects.all().delete()
            ReconciliationMatch.objects.all().delete()
            StatementEntry.objects.all().delete()
            StatementImport.objects.all().delete()
            TellerSubmission.objects.all().delete()
            Notification.objects.all().delete()
            # The audit log refuses bulk deletes by design; a reset is the only place we bypass it.
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM core_auditlog")
            User.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing data deleted."))

        for code, name in BRANCHES:
            Branch.objects.get_or_create(code=code, defaults={"name": name})
        for code, name in BANKS:
            Bank.objects.get_or_create(code=code, defaults={"name": name})
        for name, email, role, branch_code in USERS:
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(email=email, password=DEMO_PASSWORD, name=name, role=role,
                                         branch=Branch.objects.get(code=branch_code) if branch_code else None)

        mandiri = Bank.objects.get(code="MANDIRI")
        created = 0
        for email, sender, holder, relation, method, amount, reference in RECEIPTS:
            if TellerSubmission.objects.filter(sender_name=sender, bank_reference_no=reference).exists():
                continue
            create_submission(user=User.objects.get(email=email), data={
                "client_uuid": uuid.uuid4(), "sender_name": sender, "account_holder_name": holder, "relationship": relation,
                "bank": mandiri, "amount": Decimal(amount), "bank_reference_no": reference, "payment_method_code": method})
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Demo data ready ({created} new receipts)."))
        self.stdout.write("Sign in with password: " + DEMO_PASSWORD)
        for _, email, role, _ in USERS:
            self.stdout.write(f"  {role:8} {email}")
        self.stdout.write("Next: sign in as finance@demo.test and upload sample_data/mandiri_statement_2026-09-30.csv")
