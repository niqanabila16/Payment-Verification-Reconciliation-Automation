"""Turns reconciliation results into notifications (BR: teller is notified automatically, no confirmation)."""
from collections import defaultdict

from apps.accounts.models import Role
from apps.core.notifications import notify_role, notify_users, send_digest_email

from ..models import MatchStatus

TELLER_TEXT = {
    MatchStatus.GFP: "was verified (GFP)",
    MatchStatus.TYPO: "looks like a typo and is waiting for Finance",
    MatchStatus.MANUAL_REVIEW: "needs manual review by Finance (amount difference)",
    MatchStatus.NOT_FOUND: "was not found in the bank statement yet",
}


def describe(sub) -> str:
    return f"Receipt #{sub.pk} (ref {sub.bank_reference_no}, RM {sub.amount:,.2f})"


def notify_run_results(transitions, summary, quiet: bool = False) -> None:
    """One notification per teller per receipt, plus ONE summary for Finance (avoids 500 pings)."""
    per_teller = defaultdict(list)
    for match, decision in transitions:
        sub = match.teller_submission
        if sub.submitted_by_id and decision.status in TELLER_TEXT:
            notify_users([sub.submitted_by], f"result_{decision.status}",
                         f"{describe(sub)} {TELLER_TEXT[decision.status]}.", "submission", sub.pk)
            per_teller[sub.submitted_by].append(f"{describe(sub)} {TELLER_TEXT[decision.status]}.")
    for teller, lines in per_teller.items():
        send_digest_email(teller, "Payment reconciliation results", lines)

    attention = summary.typo + summary.manual_review + summary.not_found
    if summary.evaluated and not quiet:
        notify_role(Role.FINANCE, "reconciliation_run",
                    f"Reconciliation finished: {summary.gfp} verified, {summary.typo} typo, "
                    f"{summary.manual_review} manual review, {summary.not_found} not found. "
                    f"{attention} item(s) need attention.", "", None)
