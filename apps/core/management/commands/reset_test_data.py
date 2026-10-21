"""
Delete test data so the same scenario can be tried again (development only). Users, branches, banks and dropdown values stay.

    python manage.py reset_test_data --yes                 # receipts, matches, bank statements, notifications, audit trail
    python manage.py reset_test_data --yes --cards         # also card uploads, cards and activation requests (+ PDF files)
    python manage.py reset_test_data --yes --receipts-only # only Teller receipts (their matches); bank rows become Open Items again
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.cards.models import ActivationRequest, Card, CardUpload
from apps.core.models import Notification
from apps.receipts.models import TellerSubmission
from apps.reconciliation.models import ReconciliationMatch, StatementEntry, StatementImport


class Command(BaseCommand):
    help = "Delete receipts, matches, bank statement data and notifications (keeps users and master data)."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Required: confirm that the data may be deleted.")
        parser.add_argument("--cards", action="store_true", help="Also delete card uploads, cards and activation requests.")
        parser.add_argument("--receipts-only", action="store_true", help="Delete only receipts (and their matches); keep bank statements.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Add --yes to confirm. This deletes data and cannot be undone.")
        if not settings.DEBUG:
            raise CommandError("Refused: DJANGO_DEBUG is False. This command is for test data only.")
        counts = {"matches": ReconciliationMatch.objects.count(), "receipts": TellerSubmission.objects.count()}
        ReconciliationMatch.objects.all().delete()
        TellerSubmission.objects.all().delete()
        if not options["receipts_only"]:
            counts["bank_rows"], counts["uploads"] = StatementEntry.objects.count(), StatementImport.objects.count()
            StatementEntry.objects.all().delete()
            StatementImport.objects.all().delete()
            Notification.objects.all().delete()
            with connection.cursor() as cursor:          # the audit trail refuses bulk deletes by design; a test reset is the only exception
                cursor.execute("DELETE FROM core_auditlog")
        if options["cards"]:
            for request in ActivationRequest.objects.all():
                request.file.delete(save=False)
            counts["cards"] = Card.objects.count()
            ActivationRequest.objects.all().delete()
            Card.objects.all().delete()
            CardUpload.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted: {counts}"))
