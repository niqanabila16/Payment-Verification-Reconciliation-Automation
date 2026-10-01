"""
Marks bank statement imports that are stuck in "processing" as "failed" so Finance can upload the file again.

An import gets stuck when the server is stopped or crashes while the background thread is working.
Run it after a restart (it is also safe to run on a schedule):

    python manage.py recover_imports --minutes 10
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.audit import record
from apps.reconciliation.models import ImportStatus, StatementImport


class Command(BaseCommand):
    help = "Mark imports stuck in 'processing' as failed so they can be uploaded again."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=10, help="Age after which a processing import counts as stuck.")

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=options["minutes"])
        stuck = StatementImport.objects.filter(status=ImportStatus.PROCESSING, imported_at__lt=cutoff)
        count = 0
        for imp in stuck:
            imp.status = ImportStatus.FAILED
            imp.error_message = "Processing was interrupted (server restart or crash). Upload the file again."
            imp.save(update_fields=["status", "error_message"])
            record("import", imp.pk, "import.recovered")
            count += 1
        self.stdout.write(self.style.SUCCESS(f"{count} stuck import(s) marked as failed."))
