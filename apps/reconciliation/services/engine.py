"""
Matching engine (BR-1, BR-2, BR-6, BR-8, BR-10). Deterministic rules + RapidFuzz for the name words (ADR-0003).

A receipt is matched on the fields of the bank row that the parser extracted (nothing else of the bank file is used):

  NAME       the Teller's ACCOUNT HOLDER  vs  the bank's name (RHB: Sender`s Name, ALB: Reference 2, PBB: Reference 1).
             The Teller's "sender" is NOT compared (revision 2, point 4).
  AMOUNT     equal to the sen (the bank's Credit or Debit value).
  The REFERENCE is NOT a matching field any more (revision 3): the Teller's reference number is kept for the report and for the
  duplicate check at input time, and only breaks a tie when two free bank rows have the same name and amount.
  (Banks that print no name, MBB, cannot be matched on a name: they are matched on amount and reference.)

  1. NAME and AMOUNT match                                              -> GFP (score 100)
  2. NAME matches, AMOUNT differs and "amount" is in settings.REVIEW_REASONS
     (the free row of that name with the closest amount)                -> Review (Finance decides: GFP or Reject)
  3. otherwise                                                           -> Not found

Only rows of the SAME BANK as the receipt are considered (receipt bank RHB <-> RHB statement), and an upload only
re-evaluates the receipts of the bank that was uploaded: receipts of other banks stay Pending (revision 2, point 11).
Rows of a transaction type that is not reconciled (ALB: everything but "DuitNow CR Trf CA", PBB: everything but
"DUITNOW TRSF CR") are never matched; they are Open Items straight away.
Banks that print no name (MBB) are matched on amount and reference only.

Name rule: words are compared in any order, and at least NAME_MATCH_MIN_WORDS (default 2) words must be shared. The bank
prints the full (often truncated) name, the Teller usually types two words: "Niqa Nabila" and "Ihsani Niqa" both match
"NIQA NABILA NUR IHSANI". A word matches when it is equal, when it starts with the bank's last word (the bank cuts long
names, "HOTLINA" vs "HOTLIN"), or when RapidFuzz ratio >= NAME_WORD_MIN_SCORE (default 85, a small typo).
Titles such as BIN / BINTI are ignored. When the Teller typed fewer words than the minimum, all of them must match.

Review results only SUGGEST one bank row; Finance confirms (final link in bank_statement_entry) or rejects (the Teller then sees
"Reject" and must correct the receipt). Open items (Pending / Not found) are re-checked on EVERY upload of their bank, however
old they are (BR-10). Receipts that Finance rejected wait for the Teller's correction. Statement rows nobody claimed are "Open Items".
The company branch is never used as a filter: a payment may be reported by the wrong branch.
"""
import logging
import re
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rapidfuzz import fuzz

from apps.core.audit import record

from ..models import MatchStatus, MatchType, ReconciliationMatch, ReviewReason, StatementEntry
from .bank_profiles import PROFILES

logger = logging.getLogger(__name__)
_ENGINE_LOCK = threading.Lock()  # one matching run at a time (single-process deployment)

FIELDS = (ReviewReason.NAME.value, ReviewReason.AMOUNT.value, ReviewReason.REFERENCE.value)


@dataclass
class Decision:
    match_id: int
    status: str
    match_type: str = ""
    score: Decimal | None = None
    entry_id: int | None = None        # final link (GFP)
    suggested_id: int | None = None    # suggestion (Review)
    reasons: list = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)
    note: str = ""


@dataclass
class RunSummary:
    evaluated: int = 0
    gfp: int = 0
    manual_review: int = 0
    not_found: int = 0
    changed: list[tuple[int, str]] = field(default_factory=list)  # (match_id, new_status)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("evaluated", "gfp", "manual_review", "not_found")}


# ---------------------------------------------------------------------------------------------------------------------
# Field comparisons
# ---------------------------------------------------------------------------------------------------------------------
def reference_matches(teller_ref: str, bank_ref: str) -> bool:
    """Equal, or one contained in the other (only when the shorter one is at least REFERENCE_MIN_LENGTH characters)."""
    if not teller_ref or not bank_ref:
        return False
    if teller_ref == bank_ref:
        return True
    shorter = min(len(teller_ref), len(bank_ref))
    return shorter >= settings.REFERENCE_MIN_LENGTH and (teller_ref in bank_ref or bank_ref in teller_ref)


NAME_IGNORED_WORDS = {"BIN", "BINTI", "BTE", "BINTE", "BT", "ANAK", "SDN", "BHD", "PLT"}


def name_words(text: str) -> list[str]:
    """Upper-case words of a name: punctuation removed, single letters (initials, the A/L of 'A/L') and titles dropped."""
    return [w for w in re.sub(r"[^A-Z0-9]+", " ", (text or "").upper()).split() if len(w) >= 2 and w not in NAME_IGNORED_WORDS]


def _word_score(word: str, bank_word: str, is_last: bool) -> float:
    if word == bank_word:
        return 100.0
    if is_last and word.startswith(bank_word):      # the bank cuts long names: HOTLIN <- HOTLINA
        return 95.0
    return fuzz.ratio(word, bank_word)


def shared_name_words(teller_name: str, bank_name: str) -> tuple[int, int]:
    """(words that match, words that must match). Order does not matter; every bank word is used at most once."""
    teller, bank = name_words(teller_name), name_words(bank_name)
    minimum = settings.NAME_WORD_MIN_SCORE
    free, shared = list(range(len(bank))), 0
    for word in teller:
        scored = [(_word_score(word, bank[j], j == len(bank) - 1), j) for j in free]
        score, j = max(scored, default=(0.0, -1))
        if score >= minimum:
            free.remove(j)
            shared += 1
    return shared, min(settings.NAME_MATCH_MIN_WORDS, len(teller), len(bank))


def name_overlap(sub, entry) -> tuple[int, int]:
    """(shared, needed) between the Teller's ACCOUNT HOLDER and the bank's name. (0, 0) when either side has no name."""
    if not entry.counterparty_name or not sub.account_holder_name:
        return 0, 0
    return shared_name_words(sub.account_holder_name, entry.counterparty_name)


def name_score(sub, entry) -> int:
    """Number of shared name words, used to rank candidates."""
    return name_overlap(sub, entry)[0]


def names_match(sub, entry) -> bool:
    shared, needed = name_overlap(sub, entry)
    return needed > 0 and shared >= needed


def name_matters(bank_id: int, name_banks) -> bool:
    return bank_id in name_banks


def _name_required_bank_ids() -> set:
    """Banks whose statement prints a usable name, so the name is part of the match (RHB, ALB, PBB)."""
    formats = [k for k, p in PROFILES.items() if p.name_required]
    bank_model = StatementEntry._meta.get_field("bank").related_model
    return set(bank_model.objects.filter(statement_format__in=[*formats, *(f.upper() for f in formats)]).values_list("id", flat=True))


def failed_fields(sub, entry, needs_name: bool) -> set:
    """
    Which matching fields differ between the receipt and the bank row.
    Banks with a name: NAME and AMOUNT (the reference is not compared). Banks without a name (MBB): AMOUNT and REFERENCE.
    """
    failed = set()
    if entry.amount != sub.amount:
        failed.add(ReviewReason.AMOUNT.value)
    if needs_name:
        if not names_match(sub, entry):
            failed.add(ReviewReason.NAME.value)
    elif not reference_matches(sub.reference_normalized, entry.reference_normalized):
        failed.add(ReviewReason.REFERENCE.value)
    return failed


def review_reasons_allowed() -> set:
    return {r for r in getattr(settings, "REVIEW_REASONS", ("amount",)) if r in FIELDS}


def _rank(sub, entry) -> tuple:
    """Higher is better: smaller amount difference, more shared name words, the same reference (tie-break only), older row first."""
    exact = 1 if sub.reference_normalized == entry.reference_normalized else 0
    return (-abs(entry.amount - sub.amount), name_score(sub, entry), exact, -entry.id)


def _entry_text(sub, entry) -> str:
    return f"Teller: {sub.account_holder_name or '-'}, bank: {entry.counterparty_name or '-'}"


# ---------------------------------------------------------------------------------------------------------------------
# Decisions (pure: no database writes)
# ---------------------------------------------------------------------------------------------------------------------
def decide_perfect(match: ReconciliationMatch, rows_by_bank: dict, claimed: set, name_banks=frozenset()) -> Decision | None:
    """GFP when a free row of the receipt's bank matches name and amount."""
    sub = match.teller_submission
    needs_name = name_matters(sub.bank_id, name_banks)
    best = None
    for entry in rows_by_bank.get(sub.bank_id, ()):
        if entry.id in claimed or entry.amount != sub.amount:
            continue
        if failed_fields(sub, entry, needs_name):
            continue
        if best is None or _rank(sub, entry) > _rank(sub, best):
            best = entry
    if best is None:
        return None
    return Decision(match.id, MatchStatus.GFP, MatchType.AUTO_EXACT, Decimal("100.00"), entry_id=best.id, snapshot=best.snapshot(),
                    note="Name and amount match." if needs_name else "Amount and reference match.")


def decide_review(match: ReconciliationMatch, rows_by_bank: dict, claimed: set, name_banks=frozenset()) -> Decision:
    """Review when exactly one field differs and that field is an allowed review reason; otherwise Not found."""
    sub = match.teller_submission
    needs_name = name_matters(sub.bank_id, name_banks)
    allowed = review_reasons_allowed()
    best, best_reason = None, ""
    for entry in rows_by_bank.get(sub.bank_id, ()):
        if entry.id in claimed:
            continue
        failed = failed_fields(sub, entry, needs_name)
        if len(failed) != 1:
            continue
        reason = next(iter(failed))
        if reason not in allowed:
            continue
        if best is None or _rank(sub, entry) > _rank(sub, best):
            best, best_reason = entry, reason
    if best is not None:
        if best_reason == ReviewReason.AMOUNT.value:
            note = f"The name matches but the amount differs: Teller RM {sub.amount:,.2f}, bank RM {best.amount:,.2f}."
        elif best_reason == ReviewReason.NAME.value:
            note = f"Amount and reference match but the name differs ({_entry_text(sub, best)})."
        else:
            note = f"Name and amount match but the reference differs: Teller {sub.reference_normalized}, bank {best.reference_normalized}."
        return Decision(match.id, MatchStatus.MANUAL_REVIEW, MatchType.AUTO_EXACT, Decimal("100.00"), suggested_id=best.id,
                        reasons=[best_reason], note=note)
    return Decision(match.id, MatchStatus.NOT_FOUND, note="No bank row with this name and amount yet.")


def run_matching(*, actor=None, progress=None, match_ids=None, quiet=False, promote_only=False, bank=None) -> RunSummary:
    """
    Evaluate the open receipts against the stored bank rows and save the outcomes.
    `bank` limits the run to the receipts of that bank (an upload of the RHB statement never touches ALB receipts, which stay Pending).
    `progress(done, total)` is called regularly so the UI can show a progress bar.
    `match_ids` limits the run to specific receipts (used when a receipt arrives or is corrected: it can match a row that
    is already waiting as an Open Item); `quiet=True` skips the Finance summary notification.
    `promote_only=True`: a Pending receipt that finds nothing STAYS Pending (it was not checked against a new statement,
    so it is not "Not found" yet); it only changes when a match or a suggestion is found.
    Receipts that Finance rejected (status Reject) are never evaluated until the Teller corrects them.
    """
    from apps.receipts.models import TellerSubmission

    with _ENGINE_LOCK:
        # Receipts that somehow have no match row yet get one (BR-6).
        ReconciliationMatch.objects.bulk_create(
            [ReconciliationMatch(teller_submission=s, first_seen_at=s.entered_at) for s in TellerSubmission.objects.filter(match__isnull=True)])

        now = timezone.now()
        queryset = (ReconciliationMatch.objects.filter(match_status__in=[MatchStatus.PENDING, MatchStatus.NOT_FOUND])
                    .select_related("teller_submission").order_by("first_seen_at", "id"))
        if match_ids:
            queryset = queryset.filter(id__in=match_ids)
        if bank is not None:
            queryset = queryset.filter(teller_submission__bank=bank)
        candidates = list(queryset)
        summary = RunSummary()
        if not candidates:
            return summary

        bank_ids = {m.teller_submission.bank_id for m in candidates}
        rows_by_bank: dict = defaultdict(list)
        for entry in StatementEntry.objects.filter(matchable=True, amount__gt=0, bank_id__in=bank_ids).select_related("statement_import").order_by("id"):
            rows_by_bank[entry.bank_id].append(entry)
        claimed = set(ReconciliationMatch.objects.exclude(bank_statement_entry=None).values_list("bank_statement_entry_id", flat=True))
        claimed |= set(ReconciliationMatch.objects.filter(match_status=MatchStatus.MANUAL_REVIEW)
                       .exclude(suggested_bank_statement_entry=None).values_list("suggested_bank_statement_entry_id", flat=True))

        name_banks = _name_required_bank_ids()
        decided: dict[int, Decision] = {}
        total = len(candidates)
        # Pass 1: perfect matches for every receipt first, so a bank row that is the perfect match of one receipt is never
        # taken as a Review suggestion by another receipt that was processed earlier.
        for done, match in enumerate(candidates, start=1):
            decision = decide_perfect(match, rows_by_bank, claimed, name_banks)
            if decision:
                claimed.add(decision.entry_id)
                decided[match.id] = decision
            if progress and (done % 10 == 0 or done == total):
                progress(done // 2, total)
        # Pass 2: Review suggestions (or Not found) for the rest.
        for done, match in enumerate(candidates, start=1):
            if match.id in decided:
                continue
            decision = decide_review(match, rows_by_bank, claimed, name_banks)
            if promote_only and decision.status == MatchStatus.NOT_FOUND and match.match_status == MatchStatus.PENDING:
                continue
            if decision.suggested_id:
                claimed.add(decision.suggested_id)   # a bank row can serve only one receipt
            decided[match.id] = decision
            if progress and (done % 10 == 0 or done == total):
                progress(total // 2 + done // 2, total)

        _apply([(m, decided[m.id]) for m in candidates if m.id in decided], summary, actor, now, quiet)
        return summary


@transaction.atomic
def _apply(decisions, summary: RunSummary, actor, now, quiet=False) -> None:
    """Write all decisions in one transaction and queue the notifications."""
    from .notify import notify_run_results

    transitions = []
    for match, decision in decisions:
        previous = match.match_status
        changed = previous != decision.status
        match.match_status = decision.status
        match.match_type = decision.match_type
        match.match_score = decision.score
        match.bank_statement_entry_id = decision.entry_id
        match.suggested_bank_statement_entry_id = decision.suggested_id
        match.review_reasons = decision.reasons
        match.notes = decision.note
        match.last_attempt_at = now
        match.attempt_count += 1
        if decision.status == MatchStatus.GFP:
            match.bank_snapshot = decision.snapshot
            match.matched_at = now
        if changed:
            # Moves the receipt to the top of the Finance table. Within one run, receipts that just got matched sort above the rest.
            match.status_changed_at = now + timedelta(milliseconds=1 if decision.status == MatchStatus.GFP else 0)
        match.save()
        summary.evaluated += 1
        setattr(summary, decision.status, getattr(summary, decision.status) + 1)
        if changed:
            summary.changed.append((match.id, decision.status))
            transitions.append((match, decision))
            record("match", match.id, f"match.auto_{decision.status}", actor=actor, previous=previous,
                   score=decision.score, entry=decision.entry_id or decision.suggested_id)
    notify_run_results(transitions, summary, quiet=quiet)
