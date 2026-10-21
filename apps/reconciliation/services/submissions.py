"""Creating Teller submissions together with their (initially pending) reconciliation row."""
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.audit import record
from apps.receipts.models import SyncStatus, TellerSubmission

from ..models import ReconciliationMatch
from .engine import run_matching


@transaction.atomic
def create_submission(*, user, data: dict, entered_at=None) -> tuple[TellerSubmission, bool]:
    """
    Store a receipt. Returns (submission, created).

    Idempotent on `client_uuid`: if an offline queue replays the same receipt twice the second
    call returns the existing row with created=False instead of creating a duplicate.
    """
    existing = TellerSubmission.objects.filter(client_uuid=data["client_uuid"]).first()
    if existing:
        return existing, False
    now = timezone.now()
    try:
        with transaction.atomic():
            submission = TellerSubmission.objects.create(
                client_uuid=data["client_uuid"],
                branch=user.branch,                       # branch comes from the login session, never from the form
                submitted_by=user,
                sender_name=(data.get("sender_name") or "").strip(),
                account_holder_name=data["account_holder_name"].strip(),
                relationship=data.get("relationship") or "",
                bank=data["bank"],
                amount=data["amount"],
                bank_reference_no=data["bank_reference_no"].strip(),
                payment_method_code=data["payment_method_code"],
                transaction_at=data["transaction_at"],
                entered_at=entered_at or now,
                sync_status=SyncStatus.SYNCED,
                synced_at=now,
            )
    except IntegrityError:  # two requests with the same client_uuid raced each other
        return TellerSubmission.objects.get(client_uuid=data["client_uuid"]), False
    match = ReconciliationMatch.objects.create(teller_submission=submission, first_seen_at=submission.entered_at, status_changed_at=now)
    record("submission", submission.pk, "submission.created", actor=user, branch=user.branch.code,
           amount=submission.amount, queued_offline=bool(entered_at and (now - entered_at).total_seconds() > 300))
    # A bank row that was uploaded earlier and is waiting as an Open Item can match this receipt right now.
    run_matching(actor=user, match_ids=[match.pk], quiet=True, promote_only=True)
    return submission, True
