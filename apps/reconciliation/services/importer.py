"""
Orchestrates a bank statement upload: validate -> delete bank data older than 31 days -> store new rows -> run the matching engine
for the receipts of THE UPLOADED BANK only.

The slow part runs in a background thread so the browser can show a progress bar.
The thread uses its own database connection and always closes it.

BR-1: a transaction is never stored or matched twice. Uploading the same file (or an overlapping
period) again is allowed, but every row whose Bank Ref No. is already stored is skipped.
"""
import hashlib
import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction

from apps.core.audit import record

from ..models import ImportStatus, StatementEntry, StatementImport
from .engine import run_matching
from .parser import ParsedStatement, StatementParseError, parse_statement
from .retention import purge_if_due

logger = logging.getLogger(__name__)


def find_previous_upload(file_name: str, digest: str = "") -> StatementImport | None:
    """An earlier upload with the same file name (any case) or the same content."""
    by_name = StatementImport.objects.filter(file_name__iexact=file_name).first()
    if by_name or not digest:
        return by_name
    return StatementImport.objects.filter(file_sha256=digest).first()


def read_upload(uploaded_file) -> tuple[bytes, str]:
    data = uploaded_file.read()
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise StatementParseError(f"The file is larger than {settings.MAX_UPLOAD_MB} MB. Download a shorter period from the bank.")
    return data, hashlib.sha256(data).hexdigest()


def start_import(*, user, bank, data: bytes, digest: str, file_name: str, fallback_account: str = "", fallback_date=None) -> StatementImport:
    """
    Parse the file with the reader of the selected bank and start processing.
    Raises StatementParseError (or BankMismatchError) with a readable message.
    """
    if not bank.statement_format:
        raise StatementParseError(f"{bank.name} has no statement reader. Set its statement format in Master data.")
    parsed = parse_statement(data, file_name, bank.statement_format.lower(), fallback_account, fallback_date)
    purge_if_due(interval_seconds=60)       # bank data older than 31 days goes first, so it cannot be matched against
    imp = StatementImport.objects.create(
        bank=bank, account_number=parsed.account_number, account_label=parsed.account_label,
        statement_date=parsed.statement_date, file_name=file_name[:255], file_sha256=digest,
        file_format=parsed.file_format, row_count=len(parsed.rows), status=ImportStatus.PROCESSING,
        uploaded_by=user, progress_percent=5)
    record("import", imp.pk, "import.started", actor=user, file=imp.file_name, rows=imp.row_count)

    if settings.IMPORT_RUN_SYNC:
        process_import(imp.pk, parsed, user.pk)
    else:
        threading.Thread(target=_thread_main, args=(imp.pk, parsed, user.pk), daemon=True, name=f"import-{imp.pk}").start()
    return imp


def _thread_main(import_id: int, parsed: ParsedStatement, user_id: int) -> None:
    try:
        process_import(import_id, parsed, user_id)
    finally:
        close_old_connections()  # release this thread's DB connection


def process_import(import_id: int, parsed: ParsedStatement, user_id: int) -> None:
    from apps.accounts.models import User

    imp = StatementImport.objects.get(pk=import_id)
    actor = User.objects.filter(pk=user_id).first()

    def set_progress(percent: int) -> None:
        StatementImport.objects.filter(pk=import_id).update(progress_percent=min(percent, 99))

    try:
        # 1. Store only rows that are new (same bank + account + Bank Ref No. = already known).
        known = set(StatementEntry.objects.filter(bank=imp.bank, statement_import__account_number=imp.account_number)
                    .values_list("bank_ref_no", flat=True))
        fresh = [r for r in parsed.rows if r.bank_ref_no not in known]
        skipped_overlap = len(parsed.rows) - len(fresh)
        with transaction.atomic():
            StatementEntry.objects.bulk_create([
                StatementEntry(statement_import=imp, bank=imp.bank, description=r.description,
                               debit_amount=r.debit, credit_amount=r.credit, amount=r.amount, transaction_date=r.transaction_date,
                               counterparty_name=r.counterparty_name, reference=r.reference, bank_ref_no=r.bank_ref_no,
                               reference_normalized=r.reference_normalized, matchable=r.matchable, source_row=r.source_row)
                for r in fresh])
        set_progress(40)

        # 2. Run the matching engine for the receipts of this bank; its progress covers 40% -> 95%.
        summary = run_matching(actor=actor, bank=imp.bank, progress=lambda done, total: set_progress(40 + int(55 * done / max(total, 1))))

        imp.status = ImportStatus.PROCESSED
        imp.progress_percent = 100
        imp.result_summary = {
            "bank": imp.bank.name,
            "rows_added": len(fresh),
            "rows_skipped_overlap": skipped_overlap,
            "rows_skipped_duplicate_in_file": parsed.duplicates_in_file,
            "rows_open_item_only": sum(1 for r in fresh if not r.matchable),
            "rows_skipped_invalid": parsed.skipped[:20],
            "invalid_count": len(parsed.skipped),
            **summary.as_dict(),
        }
        imp.save(update_fields=["status", "progress_percent", "result_summary"])
        record("import", imp.pk, "import.processed", actor=actor, **{k: v for k, v in imp.result_summary.items() if isinstance(v, int)})
    except Exception:  # noqa: BLE001 - the user must see a clear failure state, details go to the log
        logger.exception("Import %s failed", import_id)
        StatementImport.objects.filter(pk=import_id).update(
            status=ImportStatus.FAILED,
            error_message="The file was read but processing failed. Upload it again; rows already stored are not duplicated.")
