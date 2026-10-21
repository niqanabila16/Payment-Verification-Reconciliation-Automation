"""
Delete bank statement data older than 31 days (BANK_DATA_RETENTION_DAYS). Schedule it daily (see docs/MAINTENANCE.md).

    python manage.py purge_bank_data            # delete
    python manage.py purge_bank_data --dry-run  # only count
    python manage.py purge_bank_data --days 31
"""
from django.core.management.base import BaseCommand

from apps.reconciliation.services.retention import purge_expired


class Command(BaseCommand):
    help = "Delete bank statement uploads and rows older than the retention period."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        result = purge_expired(options["days"], dry_run=options["dry_run"])
        self.stdout.write(self.style.SUCCESS(f"{'Would delete' if options['dry_run'] else 'Deleted'}: {result}"))
