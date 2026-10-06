"""
Finance review actions on a reconciliation match. Every action:
  - checks the current status (so two Finance users cannot overwrite each other silently),
  - writes an audit log entry,
  - tells the Teller only what a Teller needs to know (verified, or a request to correct the receipt).
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Branch, User
from apps.core.audit import record
from apps.core.notifications import notify_users, notify_role

from ..models import MatchStatus, MatchType, REVIEW_STATUSES, ReconciliationMatch
from .notify import describe


class ReviewError(Exception):
    """A rule prevented the action; the message is shown to the user as-is."""


def _refresh(match: ReconciliationMatch) -> ReconciliationMatch:
    """Reload inside the transaction so the status check uses the latest value."""
    return ReconciliationMatch.objects.select_for_update().select_related("teller_submission").get(pk=match.pk)


@transaction.atomic
def confirm_suggestion(match: ReconciliationMatch, user: User, note: str = "") -> ReconciliationMatch:
    """Finance accepts the machine suggestion (typo, or amount difference) -> final match (GFP)."""
    match = _refresh(match)
    if match.match_status not in REVIEW_STATUSES or not match.suggested_bank_statement_entry_id:
        raise ReviewError("There is no pending suggestion to approve. Refresh the page; someone may have handled it already.")
    note = note.strip()
    suggested = match.suggested_bank_statement_entry
    if suggested.credit_amount != match.teller_submission.amount and not note:
        raise ReviewError("The amounts differ. Write a note explaining why this payment is accepted.")
    match.bank_statement_entry = suggested
    match.suggested_bank_statement_entry = None
    match.match_status = MatchStatus.GFP
    match.match_type = MatchType.MANUAL
    match.matched_by, match.matched_at = user, timezone.now()
    if note:
        match.notes = note
    try:
        match.save()
    except IntegrityError as exc:
        raise ReviewError("That bank row is already linked to another receipt.") from exc
    record("match", match.pk, "match.confirmed", actor=user, entry=suggested.pk, note=note)
    sub = match.teller_submission
    if sub.submitted_by_id:
        notify_users([sub.submitted_by], "result_gfp", f"{describe(sub)} was verified (GFP).", "submission", sub.pk)
    return match


@transaction.atomic
def reject_suggestion(match: ReconciliationMatch, user: User, note: str) -> ReconciliationMatch:
    """Finance says the suggestion is wrong -> back to Not found (the engine keeps looking on every upload)."""
    match = _refresh(match)
    if match.match_status not in REVIEW_STATUSES:
        raise ReviewError("There is no pending suggestion to reject.")
    if not note.strip():
        raise ReviewError("Write a short reason for rejecting the suggestion.")
    match.suggested_bank_statement_entry = None
    match.match_status = MatchStatus.NOT_FOUND
    match.match_type, match.match_score = "", None
    match.notes = f"Suggestion rejected by {user.name}: {note.strip()}"
    match.save()
    record("match", match.pk, "match.suggestion_rejected", actor=user, note=note)
    return match


@transaction.atomic
def send_feedback(match: ReconciliationMatch, user: User, message: str) -> ReconciliationMatch:
    """Finance asks the Teller to correct the receipt. One-way notification (no discussion thread)."""
    match = _refresh(match)
    if match.match_status == MatchStatus.GFP:
        raise ReviewError("This receipt is already verified.")
    if len(message.strip()) < 5:
        raise ReviewError("Write what the Teller should correct (at least 5 characters).")
    sub = match.teller_submission
    if sub.submitted_by_id:
        notify_users([sub.submitted_by], "feedback",
                     f"{describe(sub)}: Finance asks you to correct it. {message.strip()}", "submission", sub.pk)
    record("match", match.pk, "match.feedback_sent", actor=user, message=message)
    return match


@transaction.atomic
def correct_submission(match: ReconciliationMatch, user: User, data: dict) -> ReconciliationMatch:
    """
    Teller corrects a receipt that is not verified yet. The old values are kept in the audit trail,
    the match goes back to Pending and is re-evaluated immediately.
    """
    match = _refresh(match)
    if match.match_status == MatchStatus.GFP:
        raise ReviewError("This receipt is verified and can no longer be edited.")
    sub = match.teller_submission
    before = {f: str(getattr(sub, f)) for f in ("sender_name", "account_holder_name", "relationship", "bank_id",
                                                 "amount", "bank_reference_no", "payment_method_code")}
    sub.sender_name, sub.account_holder_name = data["sender_name"].strip(), data["account_holder_name"].strip()
    sub.relationship, sub.bank = data["relationship"], data["bank"]
    sub.amount, sub.bank_reference_no = data["amount"], data["bank_reference_no"].strip()
    sub.payment_method_code = data["payment_method_code"]
    sub.save()                                           # save() also refreshes reference_normalized
    match.match_status, match.match_type, match.match_score = MatchStatus.PENDING, "", None
    match.suggested_bank_statement_entry = None
    match.notes = f"Corrected by {user.name}; waiting for re-check."
    match.save()
    record("submission", sub.pk, "submission.corrected", actor=user, before=before)
    notify_role("finance", "receipt_corrected", f"{describe(sub)} was corrected by {user.name}.", "match", match.pk)
    return match


@transaction.atomic
def reassign_branch(match: ReconciliationMatch, user: User, branch: Branch) -> ReconciliationMatch:
    """
    The paying customer may have been served by a different branch than the one that reported it.
    Finance can move the receipt to the right branch; tellers of that branch are notified.
    """
    match = _refresh(match)
    sub = match.teller_submission
    if sub.branch_id == branch.pk:
        raise ReviewError("The receipt already belongs to that branch.")
    old = sub.branch
    sub.branch = branch
    sub.save(update_fields=["branch"])
    record("submission", sub.pk, "submission.branch_reassigned", actor=user, old=old.code, new=branch.code)
    notify_users(User.objects.filter(branch=branch, is_active=True), "branch_reassigned",
                 f"{describe(sub)} was moved to your branch ({branch.code}).", "submission", sub.pk)
    return match
