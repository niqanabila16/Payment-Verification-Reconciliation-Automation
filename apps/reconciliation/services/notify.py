"""Turns reconciliation results into notifications."""
from collections import defaultdict

from apps.accounts.models import Role
from apps.core.notifications import notify_role, notify_users, send_digest_email

from ..models import MatchStatus


def describe(sub) -> str:
    return f"Receipt #{sub.pk} (ref {sub.bank_reference_no}, RM {sub.amount:,.2f})"


def notify_run_results(transitions, summary, quiet: bool = False) -> None:
    """
    Tellers are notified when a receipt becomes Verified (Pending and Review look the same to them; Reject has its own message,
    sent by the review service). Finance gets ONE summary per run (not one ping per receipt).
    """
    per_teller = defaultdict(list)
    for match, decision in transitions:
        sub = match.teller_submission
        if sub.submitted_by_id and decision.status == MatchStatus.GFP:
            message = f"{describe(sub)} was verified (GFP)."
            notify_users([sub.submitted_by], "result_gfp", message, "submission", sub.pk)
            per_teller[sub.submitted_by].append(message)
    for teller, lines in per_teller.items():
        send_digest_email(teller, "Payment reconciliation results", lines)

    if summary.evaluated and not quiet:
        attention = summary.manual_review + summary.not_found
        notify_role(Role.FINANCE, "reconciliation_run",
                    f"Reconciliation finished: {summary.gfp} verified, {summary.manual_review} review, "
                    f"{summary.not_found} not found. {attention} item(s) need attention.", "", None)
