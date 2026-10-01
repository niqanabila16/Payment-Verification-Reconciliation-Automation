"""
Matching engine (REQ-F-1.1, BR-1, BR-2, BR-6, BR-8). Deterministic rules + RapidFuzz (ADR-0003).

For every open Teller submission the engine looks at CREDIT rows of statements of the same bank:

  1. Reference equal/contained (after normalisation, BR-2) AND amount equal to the sen  -> GFP (score 100)
  2. Reference equal/contained BUT amount different                                      -> Manual review (BR-8)
  3. Amount equal AND reference similar (RapidFuzz ratio >= threshold)                   -> Typo suggestion
  4. Nothing found                                                                       -> Not found

A "typo" or "manual review" result only SUGGESTS a bank row. Finance must confirm it
(the final link is stored in bank_statement_entry, the suggestion in suggested_bank_statement_entry).
The company branch is never used as a filter: a payment may be reported by the wrong branch.
"""
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rapidfuzz import fuzz

from apps.core.audit import record
from apps.core.normalize import normalize_reference

from ..models import (MatchStatus, MatchType, ReconciliationMatch, StatementEntry)

logger = logging.getLogger(__name__)
_ENGINE_LOCK = threading.Lock()  # one matching run at a time (single-process deployment)


@dataclass
class Decision:
    match_id: int
    status: str
    match_type: str = ""
    score: Decimal | None = None
    entry_id: int | None = None        # final link (GFP)
    suggested_id: int | None = None    # suggestion (typo / manual review)
    note: str = ""


@dataclass
class RunSummary:
    evaluated: int = 0
    gfp: int = 0
    typo: int = 0
    manual_review: int = 0
    not_found: int = 0
    changed: list[tuple[int, str]] = field(default_factory=list)  # (match_id, new_status)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("evaluated", "gfp", "typo", "manual_review", "not_found")}


def _entry_refs(entry: StatementEntry) -> list[str]:
    """Every normalised reference-like value on a bank row."""
    values = {normalize_reference(entry.reference_1), normalize_reference(entry.reference_2),
              normalize_reference(entry.bank_ref_no), entry.reference_normalized}
    return [v for v in values if v]


def _name_score(match: ReconciliationMatch, entry: StatementEntry) -> float:
    """Informational similarity between teller names and the bank's counterparty name."""
    if not entry.counterparty_name:
        return 0.0
    sub = match.teller_submission
    return max(fuzz.token_set_ratio(sub.sender_name.upper(), entry.counterparty_name.upper()),
               fuzz.token_set_ratio(sub.account_holder_name.upper(), entry.counterparty_name.upper()))


def decide(match: ReconciliationMatch, entries_by_amount: dict[Decimal, list[StatementEntry]],
           all_entries: list[StatementEntry], claimed: set[int]) -> Decision:
    """Pure decision for one submission (no database writes)."""
    sub = match.teller_submission
    ref = sub.reference_normalized
    available = [e for e in all_entries if e.id not in claimed]

    # 1 & 2 -- reference hit (equal or contained)
    if ref:
        hits = [e for e in available if any(ref == r or ref in r for r in _entry_refs(e))]
        same_amount = [e for e in hits if e.credit_amount == sub.amount]
        if same_amount:
            return Decision(match.id, MatchStatus.GFP, MatchType.AUTO_EXACT, Decimal("100.00"), entry_id=same_amount[0].id,
                            note="Reference and amount match exactly.")
        if hits:
            hit = hits[0]
            return Decision(match.id, MatchStatus.MANUAL_REVIEW, MatchType.AUTO_EXACT, Decimal("100.00"),
                            suggested_id=hit.id,
                            note=f"Reference matches but the amount differs: Teller RM {sub.amount:,.2f} vs bank RM {hit.credit_amount:,.2f}. "
                                 "No tolerance is allowed (BR-8), so Finance must review it.")

    # 3 -- same amount, similar reference
    best, best_key = None, (-1.0, -1.0)
    for entry in entries_by_amount.get(sub.amount, []):
        if entry.id in claimed:
            continue
        ref_score = max((fuzz.ratio(ref, r) for r in _entry_refs(entry)), default=0.0)
        key = (ref_score, _name_score(match, entry))
        if key > best_key:
            best, best_key = entry, key
    if best is not None and best_key[0] >= settings.MATCH_TYPO_MIN_SCORE:
        return Decision(match.id, MatchStatus.TYPO, MatchType.AUTO_FUZZY, Decimal(str(round(best_key[0], 2))),
                        suggested_id=best.id,
                        note=f"Amount matches and the reference is {best_key[0]:.0f}% similar. "
                             "Likely a typo by the teller; confirm or reject the suggestion.")

    # 4 -- nothing
    return Decision(match.id, MatchStatus.NOT_FOUND, note="No credit row with this reference or a similar one was found yet. "
                    "The engine retries on every new statement until the re-check window ends.")


def run_matching(*, actor=None, progress=None, match_ids=None, quiet=False) -> RunSummary:
    """
    Evaluate every open submission against all credit rows and save the outcomes.
    `progress(done, total)` is called regularly so the UI can show a progress bar.
    Safe to call repeatedly: finalised matches (GFP / closed / awaiting Finance) are left alone.
    `match_ids` limits the run to specific matches (used after a Teller corrects a receipt);
    `quiet=True` skips the Finance summary notification.
    """
    from apps.receipts.models import TellerSubmission

    with _ENGINE_LOCK:
        # Submissions that somehow have no match row yet (e.g. restored data) get one (BR-6).
        orphans = TellerSubmission.objects.filter(match__isnull=True)
        ReconciliationMatch.objects.bulk_create(
            [ReconciliationMatch(teller_submission=s, first_seen_at=s.entered_at) for s in orphans])

        now = timezone.now()
        window = settings.RECHECK_WINDOW_DAYS
        candidates = [
            m for m in ReconciliationMatch.objects
            .filter(match_status__in=[MatchStatus.PENDING, MatchStatus.NOT_FOUND])
            .filter(**({"id__in": match_ids} if match_ids else {}))
            .select_related("teller_submission", "teller_submission__bank")
            .order_by("first_seen_at", "id")
            # pending items are always evaluated once; not_found items stop being retried after the window
            if m.match_status == MatchStatus.PENDING or (now - m.first_seen_at).days < window
        ]
        summary = RunSummary()
        if not candidates:
            return summary

        # Credit rows grouped per bank; rows already used (or suggested) elsewhere are "claimed".
        entries = list(StatementEntry.objects.filter(credit_amount__gt=0).select_related("statement_import"))
        by_bank: dict[int, list[StatementEntry]] = defaultdict(list)
        for entry in entries:
            by_bank[entry.statement_import.bank_id].append(entry)
        by_bank_amount: dict[int, dict[Decimal, list[StatementEntry]]] = {}
        for bank_id, rows in by_bank.items():
            grouped: dict[Decimal, list[StatementEntry]] = defaultdict(list)
            for row in rows:
                grouped[row.credit_amount].append(row)
            by_bank_amount[bank_id] = grouped
        claimed = set(ReconciliationMatch.objects.exclude(bank_statement_entry=None).values_list("bank_statement_entry_id", flat=True))
        claimed |= set(ReconciliationMatch.objects.filter(match_status__in=[MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW])
                       .exclude(suggested_bank_statement_entry=None).values_list("suggested_bank_statement_entry_id", flat=True))

        decisions: list[tuple[ReconciliationMatch, Decision]] = []
        total = len(candidates)
        for done, match in enumerate(candidates, start=1):
            bank_id = match.teller_submission.bank_id
            decision = decide(match, by_bank_amount.get(bank_id, {}), by_bank.get(bank_id, []), claimed)
            for taken in (decision.entry_id, decision.suggested_id):
                if taken:
                    claimed.add(taken)   # an entry can serve only one submission
            decisions.append((match, decision))
            if progress and (done % 10 == 0 or done == total):
                progress(done, total)

        _apply(decisions, summary, actor, now, quiet)
        return summary


@transaction.atomic
def _apply(decisions, summary: RunSummary, actor, now, quiet=False) -> None:
    """Write all decisions in one transaction and queue the notifications."""
    from .notify import notify_run_results

    transitions = []
    for match, decision in decisions:
        previous = match.match_status
        match.match_status = decision.status
        match.match_type = decision.match_type
        match.match_score = decision.score
        match.bank_statement_entry_id = decision.entry_id
        match.suggested_bank_statement_entry_id = decision.suggested_id
        match.notes = decision.note
        match.last_attempt_at = now
        match.attempt_count += 1
        if decision.status == MatchStatus.GFP:
            match.matched_at = now
        match.save()
        summary.evaluated += 1
        setattr(summary, decision.status, getattr(summary, decision.status) + 1)
        if previous != decision.status:
            summary.changed.append((match.id, decision.status))
            transitions.append((match, decision))
            record("match", match.id, f"match.auto_{decision.status}", actor=actor, previous=previous,
                   score=decision.score, entry=decision.entry_id or decision.suggested_id)
    notify_run_results(transitions, summary, quiet=quiet)
