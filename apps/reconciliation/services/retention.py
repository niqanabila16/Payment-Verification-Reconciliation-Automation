"""
Retention of bank data (revision 2, point 15): everything that came from a bank statement is deleted 31 days after the
file was uploaded (settings.BANK_DATA_RETENTION_DAYS).

Deleted: upload history rows (StatementImport) and all their bank rows (StatementEntry).
Kept:    Teller receipts, their status and notes, the audit trail, and for verified receipts a snapshot of the bank row
         (ReconciliationMatch.bank_snapshot), so the comparison screen of a GFP receipt keeps working.
A receipt that was waiting for a decision on a deleted bank row (Review) goes back to Pending.

Runs (1) before every statement upload, (2) at most once an hour when Finance opens the Reconciliation page, and
(3) from the command `python manage.py purge_bank_data` (schedule it daily, see docs/MAINTENANCE.md).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.audit import record

from ..models import MatchStatus, ReconciliationMatch, StatementEntry, StatementImport

logger = logging.getLogger(__name__)
THROTTLE_KEY = "bank-data-purge-ran"


def cutoff(days: int | None = None, now=None):
    days = settings.BANK_DATA_RETENTION_DAYS if days is None else days
    return (now or timezone.now()) - timedelta(days=days)


@transaction.atomic
def purge_expired(days: int | None = None, *, dry_run: bool = False, actor=None, now=None) -> dict:
    """Delete bank data older than `days` (default 31). Returns counts."""
    limit = cutoff(days, now)
    old_imports = StatementImport.objects.filter(imported_at__lt=limit)
    import_ids = list(old_imports.values_list("id", flat=True))
    counts = {"imports": len(import_ids), "entries": 0, "reviews_reset": 0, "cutoff": limit.isoformat()}
    if not import_ids:
        return counts
    entries = StatementEntry.objects.filter(statement_import_id__in=import_ids)
    counts["entries"] = entries.count()
    reviews = ReconciliationMatch.objects.filter(match_status=MatchStatus.MANUAL_REVIEW, suggested_bank_statement_entry__in=entries)
    counts["reviews_reset"] = reviews.count()
    if dry_run:
        return counts
    now = now or timezone.now()
    for match in reviews:       # their suggestion disappears with the bank row: check them again on the next upload
        match.suggested_bank_statement_entry = None
        match.match_status, match.match_type, match.match_score, match.review_reasons = MatchStatus.PENDING, "", None, []
        match.notes = "The bank row was deleted (older than the retention period); waiting for a new statement."
        match.status_changed_at = now
        match.save()
    entries.delete()            # FKs from matches are SET_NULL (verified matches keep bank_snapshot)
    old_imports.delete()
    record("import", 0, "bank_data.purged", actor=actor, imports=counts["imports"], entries=counts["entries"], older_than=limit.date().isoformat())
    logger.info("Purged %s bank statement upload(s) and %s row(s) older than %s", counts["imports"], counts["entries"], limit)
    return counts


def purge_if_due(interval_seconds: int = 3600) -> dict | None:
    """Cheap hook for web requests: purge at most once per `interval_seconds` per process."""
    if not cache.add(THROTTLE_KEY, 1, interval_seconds):
        return None
    try:
        return purge_expired()
    except Exception:  # noqa: BLE001 - housekeeping must never break the page
        logger.exception("Automatic purge of old bank data failed")
        return None
