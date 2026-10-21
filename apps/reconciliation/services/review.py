"""
Finance review actions on a reconciliation match. Every action:
  - checks the current status (so two Finance users cannot overwrite each other silently),
  - writes an audit log entry,
  - tells the Teller only what a Teller needs to know (verified, or Reject with the note of Finance).

Finance decides from the DETAIL page with one Note and two buttons: GFP or Reject.
  GFP     the receipt is verified. Needs a bank row to link (the suggestion of a Review, or the row that was rejected earlier);
          the note is mandatory when the amounts differ.
  Reject  the Teller sees status "Reject" with the note, at the top of the receipt list, and corrects the receipt. The
          correction sets the status back to Pending and the engine checks it again.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Branch, User
from apps.core.audit import record
from apps.core.notifications import notify_role, notify_users

from apps.receipts.models import submission_fingerprint

from ..models import MatchStatus, MatchType, ReconciliationMatch
from .notify import describe


class ReviewError(Exception):
    """A rule prevented the action; the message is shown to the user as-is."""


def _refresh(match: ReconciliationMatch) -> ReconciliationMatch:
    """Reload inside the transaction so the status check uses the latest value."""
    # of=("self",): lock only the match row. PostgreSQL refuses FOR UPDATE on the nullable side of the outer joins below.
    return ReconciliationMatch.objects.select_for_update(of=("self",)).select_related(
        "teller_submission", "suggested_bank_statement_entry", "rejected_bank_statement_entry",
        "suggested_bank_statement_entry__statement_import", "rejected_bank_statement_entry__statement_import").get(pk=match.pk)


@transaction.atomic
def confirm_suggestion(match: ReconciliationMatch, user: User, note: str = "") -> ReconciliationMatch:
    """GFP: Finance accepts the compared bank row (suggestion of a Review, or the row of a Reject) -> final match."""
    match = _refresh(match)
    entry = match.suggested_bank_statement_entry or match.rejected_bank_statement_entry
    if match.match_status not in (MatchStatus.MANUAL_REVIEW, MatchStatus.REJECTED) or entry is None:
        raise ReviewError("There is no bank row to approve for this receipt. Refresh the page; someone may have handled it already.")
    note = note.strip()
    if entry.amount != match.teller_submission.amount and not note:
        raise ReviewError("The amounts differ. Write a note explaining why this payment is accepted.")
    match.bank_statement_entry = entry
    match.bank_snapshot = entry.snapshot()
    match.suggested_bank_statement_entry = None
    match.rejected_bank_statement_entry = None
    match.match_status = MatchStatus.GFP
    match.match_type = MatchType.MANUAL
    match.matched_by, match.matched_at = user, timezone.now()
    match.status_changed_at = match.matched_at
    if note:
        match.finance_note = note
    try:
        match.save()
    except IntegrityError as exc:
        raise ReviewError("That bank row is already linked to another receipt.") from exc
    record("match", match.pk, "match.confirmed", actor=user, entry=entry.pk, note=note)
    sub = match.teller_submission
    if sub.submitted_by_id:
        notify_users([sub.submitted_by], "result_gfp", f"{describe(sub)} was verified (GFP).", "submission", sub.pk)
    return match


# The reasons Finance can pick when it rejects a receipt (dropdown on the detail page). The stored note is the chosen text.
REJECT_REASONS = ("Nama Beda", "Amaun Salah", "lain-lain")
OTHER_REASON = "lain-lain"


@transaction.atomic
def reject_receipt(match: ReconciliationMatch, user: User, reason: str, detail: str = "") -> ReconciliationMatch:
    """
    Reject: the Teller sees "Reject" and the reason. The compared bank row stays visible on the detail page.
    `reason` must be one of REJECT_REASONS; `detail` is an optional extra remark that is only kept for "lain-lain".
    """
    match = _refresh(match)
    if match.match_status == MatchStatus.GFP:
        raise ReviewError("This receipt is already verified.")
    if match.match_status == MatchStatus.REJECTED:
        raise ReviewError("This receipt is already rejected. It waits for the teller's correction.")
    reason = (reason or "").strip()
    if reason not in REJECT_REASONS:
        raise ReviewError("Choose a reason for the Reject.")
    detail = (detail or "").strip()[:200]
    note = f"{reason}: {detail}" if reason == OTHER_REASON and detail else reason
    previous = match.match_status
    if match.suggested_bank_statement_entry_id:
        match.rejected_bank_statement_entry = match.suggested_bank_statement_entry
    match.suggested_bank_statement_entry = None
    match.match_status = MatchStatus.REJECTED
    match.match_type, match.match_score = "", None
    match.notes = "Rejected by Finance. Waiting for the teller's correction."
    match.finance_note = note
    match.matched_by = user
    match.status_changed_at = timezone.now()
    match.save()
    record("match", match.pk, "match.rejected", actor=user, previous=previous, note=note)
    sub = match.teller_submission
    if sub.submitted_by_id:
        notify_users([sub.submitted_by], "rejected", f"{describe(sub)} was rejected by Finance: {note}", "submission", sub.pk)
    return match


@transaction.atomic
def correct_submission(match: ReconciliationMatch, user: User, data: dict) -> ReconciliationMatch:
    """
    Teller corrects a receipt that is not verified yet (typically after a Reject). The old values are kept in the audit trail and
    as a fingerprint (so repeating them is recognised), the match goes back to Pending and is re-evaluated immediately.
    """
    match = _refresh(match)
    if match.match_status == MatchStatus.GFP:
        raise ReviewError("This receipt is verified and can no longer be edited.")
    sub = match.teller_submission
    before = {f: str(getattr(sub, f)) for f in ("sender_name", "account_holder_name", "relationship", "bank_id", "amount",
                                                 "bank_reference_no", "payment_method_code", "transaction_at")}
    old_fingerprint = sub.fingerprint
    new_fingerprint = submission_fingerprint(data.get("sender_name"), data["account_holder_name"], data.get("relationship") or "", data["bank"].pk,
                                             data["amount"], data["bank_reference_no"], data["payment_method_code"], data["transaction_at"])
    if new_fingerprint == old_fingerprint or new_fingerprint in (sub.previous_versions or []):
        raise ReviewError("These values were already entered for this receipt. Correct what Finance asked for before saving.")
    sub.sender_name, sub.account_holder_name = (data.get("sender_name") or "").strip(), data["account_holder_name"].strip()
    sub.relationship, sub.bank = data.get("relationship") or "", data["bank"]
    sub.amount, sub.bank_reference_no = data["amount"], data["bank_reference_no"].strip()
    sub.payment_method_code = data["payment_method_code"]
    sub.transaction_at = data["transaction_at"]
    if old_fingerprint not in (sub.previous_versions or []):
        sub.previous_versions = [*(sub.previous_versions or []), old_fingerprint]
    sub.save()                                           # save() also refreshes reference_normalized
    was = match.match_status
    match.match_status, match.match_type, match.match_score = MatchStatus.PENDING, "", None
    match.suggested_bank_statement_entry = None
    match.rejected_bank_statement_entry = None
    match.review_reasons = []
    match.finance_note = ""
    match.notes = f"Corrected by {user.name}; waiting for re-check."
    match.status_changed_at = timezone.now()
    match.save()
    record("submission", sub.pk, "submission.corrected", actor=user, before=before, previous_status=was)
    notify_role("finance", "receipt_corrected", f"{describe(sub)} was corrected by {user.name}.", "match", match.pk)
    return match
