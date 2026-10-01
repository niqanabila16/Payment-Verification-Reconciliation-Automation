"""
Finance review actions on a reconciliation match. Every action:
  - checks the current status (so two Finance users cannot overwrite each other silently),
  - writes an audit log entry,
  - notifies the Teller who reported the receipt.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone
from rapidfuzz import fuzz

from apps.accounts.models import Branch, User
from apps.core.audit import record
from apps.core.notifications import notify_users

from ..models import MatchStatus, MatchType, ReconciliationMatch, StatementEntry
from .notify import describe


class ReviewError(Exception):
    """A rule prevented the action; the message is shown to the user as-is."""


def _teller_notice(match: ReconciliationMatch, text: str, kind: str) -> None:
    sub = match.teller_submission
    if sub.submitted_by_id:
        notify_users([sub.submitted_by], kind, f"{describe(sub)} {text}", "submission", sub.pk)


def _refresh(match: ReconciliationMatch) -> ReconciliationMatch:
    """Reload inside the transaction so the status check uses the latest value."""
    return ReconciliationMatch.objects.select_for_update().select_related("teller_submission").get(pk=match.pk)


@transaction.atomic
def confirm_suggestion(match: ReconciliationMatch, user: User, note: str = "") -> ReconciliationMatch:
    """Finance accepts the machine suggestion (typo, or amount difference) -> final match."""
    match = _refresh(match)
    if match.match_status not in (MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW) or not match.suggested_bank_statement_entry_id:
        raise ReviewError("There is no pending suggestion to confirm. Refresh the page; someone may have handled it already.")
    note = note.strip()
    suggested = match.suggested_bank_statement_entry
    if suggested.credit_amount != match.teller_submission.amount and not note:
        raise ReviewError("The amounts differ. Write a note explaining why this payment is accepted before confirming.")
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
    _teller_notice(match, "was confirmed by Finance and is now verified (GFP).", "result_gfp")
    return match


@transaction.atomic
def reject_suggestion(match: ReconciliationMatch, user: User, note: str) -> ReconciliationMatch:
    """Finance says the suggestion is wrong -> back to 'not found' (the engine keeps looking)."""
    match = _refresh(match)
    if match.match_status not in (MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW):
        raise ReviewError("There is no pending suggestion to reject.")
    if not note.strip():
        raise ReviewError("Write a short reason so the Teller knows what to check.")
    match.suggested_bank_statement_entry = None
    match.match_status = MatchStatus.NOT_FOUND
    match.match_type, match.match_score = "", None
    match.notes = f"Suggestion rejected by {user.name}: {note.strip()}"
    match.save()
    record("match", match.pk, "match.suggestion_rejected", actor=user, note=note)
    _teller_notice(match, f"was not matched. Finance note: {note.strip()}", "result_not_found")
    return match


@transaction.atomic
def link_manually(match: ReconciliationMatch, user: User, entry_id: int, note: str) -> ReconciliationMatch:
    """Finance links a specific bank row by hand (a note is always required)."""
    match = _refresh(match)
    if match.match_status in (MatchStatus.GFP, MatchStatus.CLOSED):
        raise ReviewError("This item is already final and cannot be linked again.")
    if not note.strip():
        raise ReviewError("Write a note explaining why this bank row belongs to the receipt.")
    entry = StatementEntry.objects.filter(pk=entry_id, credit_amount__gt=0).first()
    if entry is None:
        raise ReviewError("That bank row no longer exists or is not a credit.")
    if entry.statement_import.bank_id != match.teller_submission.bank_id:
        raise ReviewError("The bank row belongs to a different bank than the receipt.")
    match.bank_statement_entry = entry
    match.suggested_bank_statement_entry = None
    match.match_status, match.match_type = MatchStatus.GFP, MatchType.MANUAL
    match.matched_by, match.matched_at = user, timezone.now()
    match.notes = note.strip()
    try:
        match.save()
    except IntegrityError as exc:
        raise ReviewError("That bank row is already linked to another receipt. Pick a different row.") from exc
    record("match", match.pk, "match.linked_manually", actor=user, entry=entry.pk, note=note)
    _teller_notice(match, "was linked to a bank row by Finance and is now verified (GFP).", "result_gfp")
    return match


@transaction.atomic
def close_match(match: ReconciliationMatch, user: User, reason: str) -> ReconciliationMatch:
    """Close an unresolved item. A reason is mandatory (DBML: closed_reason required when closed)."""
    match = _refresh(match)
    if match.match_status in (MatchStatus.GFP, MatchStatus.CLOSED):
        raise ReviewError("This item is already final.")
    if len(reason.strip()) < 10:
        raise ReviewError("Explain why the item is closed (at least 10 characters). The reason is kept for audit.")
    match.match_status = MatchStatus.CLOSED
    match.suggested_bank_statement_entry = None
    match.closed_reason, match.closed_at = reason.strip(), timezone.now()
    match.matched_by = user
    match.save()
    record("match", match.pk, "match.closed", actor=user, reason=reason)
    _teller_notice(match, f"was closed by Finance. Reason: {reason.strip()}", "result_closed")
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
                 f"{describe(sub)} was moved to your branch ({branch.code}) by Finance.", "submission", sub.pk)
    return match


def candidate_entries(match: ReconciliationMatch, limit: int = 8):
    """Unlinked credit rows of the same bank, most similar reference first (for manual linking)."""
    sub = match.teller_submission
    linked = set(ReconciliationMatch.objects.exclude(bank_statement_entry=None).values_list("bank_statement_entry_id", flat=True))
    rows = (StatementEntry.objects.filter(credit_amount__gt=0, statement_import__bank_id=sub.bank_id)
            .exclude(pk__in=linked).select_related("statement_import").order_by("-id")[:500])
    scored = []
    for row in rows:
        best = max((fuzz.ratio(sub.reference_normalized, r) for r in (row.reference_normalized, row.bank_ref_no.upper()) if r), default=0)
        same_amount = row.credit_amount == sub.amount
        scored.append((same_amount, best, row))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [{"entry": r, "ref_score": round(s), "same_amount": a} for a, s, r in scored[:limit]]


@transaction.atomic
def send_feedback(match: ReconciliationMatch, user: User, message: str) -> ReconciliationMatch:
    """
    Finance asks the Teller to correct the input data (REVIEW flow). The message is stored in the
    discussion thread and the Teller is notified; the item stays in review until it is corrected.
    """
    from ..models import MatchComment

    match = _refresh(match)
    if match.match_status in (MatchStatus.GFP, MatchStatus.CLOSED):
        raise ReviewError("This item is already final.")
    if len(message.strip()) < 5:
        raise ReviewError("Write what the Teller should correct (at least 5 characters).")
    MatchComment.objects.create(reconciliation_match=match, author=user, comment=f"Please correct this receipt: {message.strip()}")
    record("match", match.pk, "match.feedback_sent", actor=user, message=message)
    _teller_notice(match, f"needs a correction. Finance says: {message.strip()}", "feedback")
    return match


EDITABLE_STATUSES = (MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW, MatchStatus.NOT_FOUND)


@transaction.atomic
def correct_submission(match: ReconciliationMatch, user: User, data: dict) -> ReconciliationMatch:
    """
    Teller corrects a receipt that is in review / not found. The old values are kept in the audit
    trail, the match goes back to Pending and is re-evaluated immediately.
    """
    from apps.core.notifications import notify_role

    match = _refresh(match)
    if match.match_status not in EDITABLE_STATUSES:
        raise ReviewError("This receipt can no longer be edited because it is verified, closed or still pending.")
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
    notify_role("finance", "receipt_corrected", f"{describe(sub)} was corrected by {user.name} and re-checked.", "match", match.pk)
    return match
