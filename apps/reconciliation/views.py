"""Finance screens: reconciliation queue, match detail (side-by-side), bank statement uploads."""
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from rapidfuzz import fuzz

from apps.accounts.models import Branch, Role
from apps.core.audit import record
from apps.core.notifications import notify_role, notify_users
from apps.core.permissions import role_required

from .forms import CommentForm, ReassignForm, StatementUploadForm
from .models import (ATTENTION_STATUSES, MatchComment, MatchStatus, ReconciliationMatch,
                     StatementImport)
from .services import review
from .services.importer import start_import
from .services.notify import describe
from .services.parser import StatementParseError

TABS = [
    ("attention", "Needs attention", [MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW, MatchStatus.NOT_FOUND]),
    ("review", "Review", [MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW]),
    ("unmatched", "Unmatched", [MatchStatus.NOT_FOUND]),
    ("pending", "Pending", [MatchStatus.PENDING]),
    ("verified", "Verified", [MatchStatus.GFP]),
    ("closed", "Closed", [MatchStatus.CLOSED]),
    ("all", "All", None),
]


@role_required(Role.FINANCE, Role.ADMIN)
def queue(request):
    """REQ-F-1.2: queue of items that are not matched yet, oldest first."""
    tab = request.GET.get("tab", "attention")
    tab_map = {key: statuses for key, _, statuses in TABS}
    if tab not in tab_map:
        tab = "attention"
    base = ReconciliationMatch.objects.select_related("teller_submission", "teller_submission__branch",
                                                      "teller_submission__bank", "teller_submission__submitted_by")
    q = request.GET.get("q", "").strip()
    branch = request.GET.get("branch", "")
    if q:
        base = base.filter(Q(teller_submission__bank_reference_no__icontains=q)
                           | Q(teller_submission__reference_normalized__icontains=q.upper().replace(" ", "").replace("-", ""))
                           | Q(teller_submission__sender_name__icontains=q)
                           | Q(teller_submission__account_holder_name__icontains=q))
    if branch.isdigit():
        base = base.filter(teller_submission__branch_id=int(branch))

    # One query gives the counts for every tab and KPI card.
    counts = base.aggregate(**{key: Count("id", filter=Q(match_status__in=statuses) if statuses else None)
                               for key, _, statuses in TABS})
    statuses = tab_map[tab]
    qs = base.filter(match_status__in=statuses) if statuses else base
    page = Paginator(qs.order_by("first_seen_at", "id"), 20).get_page(request.GET.get("page"))
    for item in page.object_list:
        item.aged = item.is_aged and item.is_open

    window = timezone.now() - timedelta(days=31)
    kpis = {
        "needs_attention": counts["attention"],
        "unmatched": counts["unmatched"],
        "verified": counts["verified"],
        "aged": base.filter(match_status__in=ATTENTION_STATUSES, first_seen_at__lte=window).count(),
    }
    return render(request, "reconciliation/queue.html", {
        "page": page, "tab": tab, "tabs": [(k, label, counts[k]) for k, label, _ in TABS],
        "q": q, "branch": branch, "branches": Branch.objects.all(), "kpis": kpis,
    })


# --------------------------------------------------------------------------
# Detail (REQ-F-1.1 AC7 side-by-side, REQ-F-1.2 AC3 highlight differing fields)
# --------------------------------------------------------------------------
def _comparison(match: ReconciliationMatch):
    """Build the rows of the side-by-side table. state: 'same' | 'diff' | 'info'."""
    sub = match.teller_submission
    entry = match.bank_statement_entry or match.suggested_bank_statement_entry
    if entry is None:
        return None, None
    refs = [r for r in {entry.reference_normalized, entry.bank_ref_no.upper(),
                        "".join(ch for ch in entry.reference_1.upper() if ch.isalnum()),
                        "".join(ch for ch in entry.reference_2.upper() if ch.isalnum())} if r]
    best_ref = max(refs, key=lambda r: (sub.reference_normalized in r, fuzz.ratio(sub.reference_normalized, r)), default="")
    amount_state = "same" if entry.credit_amount == sub.amount else "diff"
    name_score = max(fuzz.token_set_ratio(sub.sender_name.upper(), entry.counterparty_name.upper()),
                     fuzz.token_set_ratio(sub.account_holder_name.upper(), entry.counterparty_name.upper())) if entry.counterparty_name else 0
    rows = [
        {"label": "Reference", "kind": "reference", "teller": sub.reference_normalized, "bank": best_ref,
         "teller_raw": sub.bank_reference_no, "bank_raw": entry.reference_1 or entry.reference_2 or entry.bank_ref_no,
         "state": "same" if sub.reference_normalized and (sub.reference_normalized == best_ref or sub.reference_normalized in best_ref) else "diff"},
        {"label": "Amount", "kind": "amount", "teller": sub.amount, "bank": entry.credit_amount, "state": amount_state,
         "hint": None if amount_state == "same" else f"Difference: RM {abs(entry.credit_amount - sub.amount):,.2f}"},
        {"label": "Name", "kind": "text", "teller": f"{sub.sender_name} / {sub.account_holder_name}", "bank": entry.counterparty_name or "-",
         "state": "info", "hint": f"{name_score:.0f}% similar (informational, names are not required to match exactly)"},
        {"label": "Bank", "kind": "text", "teller": sub.bank.name, "bank": entry.statement_import.bank.name, "state": "same"},
        {"label": "Date", "kind": "text", "teller": f"{timezone.localtime(sub.entered_at):%d %b %Y}",
         "bank": f"{entry.statement_import.statement_date:%d %b %Y}", "state": "info"},
        {"label": "Method / description", "kind": "text", "teller": sub.get_payment_method_code_display(),
         "bank": entry.description or "-", "state": "info"},
    ]
    return entry, rows


@role_required(Role.FINANCE, Role.ADMIN)
def detail(request, pk: int):
    match = get_object_or_404(ReconciliationMatch.objects.select_related(
        "teller_submission", "teller_submission__branch", "teller_submission__bank", "teller_submission__submitted_by",
        "bank_statement_entry", "bank_statement_entry__statement_import", "suggested_bank_statement_entry",
        "suggested_bank_statement_entry__statement_import", "matched_by"), pk=pk)
    entry, rows = _comparison(match)
    candidates = review.candidate_entries(match) if match.is_open else []
    return render(request, "reconciliation/detail.html", {
        "match": match, "sub": match.teller_submission, "entry": entry, "rows": rows,
        "has_diff": bool(rows) and any(r["state"] == "diff" for r in rows),
        "candidates": candidates, "comments": match.comments.select_related("author"),
        "comment_form": CommentForm(), "reassign_form": ReassignForm(),
        "can_act": request.user.role == Role.FINANCE,
    })


def _act(request, pk, action):
    """Run a review service function and show its error/success message."""
    match = get_object_or_404(ReconciliationMatch, pk=pk)
    try:
        action(match)
    except review.ReviewError as exc:
        messages.error(request, str(exc))
        return False, match
    return True, match


@role_required(Role.FINANCE)
@require_POST
def confirm(request, pk: int):
    ok, _ = _act(request, pk, lambda m: review.confirm_suggestion(m, request.user, request.POST.get("note", "")))
    if ok:
        messages.success(request, "Suggestion confirmed. The receipt is now verified (GFP) and the teller was notified.")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def reject(request, pk: int):
    ok, _ = _act(request, pk, lambda m: review.reject_suggestion(m, request.user, request.POST.get("note", "")))
    if ok:
        messages.success(request, "Suggestion rejected. The item is back in the Unmatched list.")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def feedback(request, pk: int):
    ok, _ = _act(request, pk, lambda m: review.send_feedback(m, request.user, request.POST.get("message", "")))
    if ok:
        messages.success(request, "Feedback sent. The teller was notified and can now correct the receipt.")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def link(request, pk: int):
    try:
        entry_id = int(request.POST.get("entry_id", ""))
    except ValueError:
        messages.error(request, "Choose a bank row to link.")
        return redirect("reconciliation:detail", pk=pk)
    ok, _ = _act(request, pk, lambda m: review.link_manually(m, request.user, entry_id, request.POST.get("note", "")))
    if ok:
        messages.success(request, "Bank row linked. The receipt is now verified (GFP).")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def close(request, pk: int):
    ok, _ = _act(request, pk, lambda m: review.close_match(m, request.user, request.POST.get("reason", "")))
    if ok:
        messages.success(request, "Item closed. The reason was saved to the audit trail.")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def reassign(request, pk: int):
    form = ReassignForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Select the branch the receipt should be moved to.")
        return redirect("reconciliation:detail", pk=pk)
    ok, _ = _act(request, pk, lambda m: review.reassign_branch(m, request.user, form.cleaned_data["branch"]))
    if ok:
        messages.success(request, f"Receipt moved to branch {form.cleaned_data['branch'].code}. Its tellers were notified.")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE, Role.TELLER)
@require_POST
def comment(request, pk: int):
    """Discussion thread. Tellers may only comment on receipts of their own branch."""
    match = get_object_or_404(ReconciliationMatch.objects.select_related("teller_submission"), pk=pk)
    sub = match.teller_submission
    is_teller = request.user.role == Role.TELLER
    if is_teller and sub.branch_id != request.user.branch_id:
        messages.error(request, "You can only comment on receipts of your own branch.")
        return redirect("receipts:list")
    form = CommentForm(request.POST)
    back = redirect("receipts:detail", pk=sub.pk) if is_teller else redirect("reconciliation:detail", pk=pk)
    if not form.is_valid():
        messages.error(request, form.errors["comment"][0])
        return back
    MatchComment.objects.create(reconciliation_match=match, author=request.user, comment=form.cleaned_data["comment"])
    record("match", match.pk, "comment.added", actor=request.user)
    text = f"{request.user.name} commented on {describe(sub)}: {form.cleaned_data['comment'][:120]}"
    if is_teller:
        notify_role(Role.FINANCE, "comment", text, "match", match.pk)
    elif sub.submitted_by_id:
        notify_users([sub.submitted_by], "comment", text, "submission", sub.pk)
    messages.success(request, "Comment sent.")
    return back


# --------------------------------------------------------------------------
# Bank statement uploads (REQ-F-1.3)
# --------------------------------------------------------------------------
@role_required(Role.FINANCE)
def import_list(request):
    form = StatementUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            imp = start_import(user=request.user, bank=data["bank"], uploaded_file=data["file"],
                               fallback_account=data.get("account_number", ""), fallback_date=data.get("statement_date"))
        except StatementParseError as exc:
            form.add_error("file", str(exc))
        else:
            return redirect("reconciliation:import_detail", pk=imp.pk)
    page = Paginator(StatementImport.objects.select_related("bank", "uploaded_by"), 10).get_page(request.GET.get("page"))
    return render(request, "reconciliation/import_list.html", {"form": form, "page": page})


@role_required(Role.FINANCE, Role.ADMIN)
def import_detail(request, pk: int):
    imp = get_object_or_404(StatementImport.objects.select_related("bank", "uploaded_by"), pk=pk)
    summary = imp.result_summary or {}
    return render(request, "reconciliation/import_detail.html", {
        "imp": imp, "summary": summary,
        "attention": summary.get("typo", 0) + summary.get("manual_review", 0) + summary.get("not_found", 0),
    })


@role_required(Role.FINANCE, Role.ADMIN)
@require_GET
def import_status(request, pk: int):
    """Polled by the progress bar."""
    imp = get_object_or_404(StatementImport, pk=pk)
    return JsonResponse({"status": imp.status, "progress": imp.progress_percent, "error": imp.error_message})


@role_required(Role.FINANCE)
@require_POST
def rerun(request):
    """Re-run the engine without a new file (e.g. after Tellers added late receipts)."""
    from .services.engine import run_matching

    summary = run_matching(actor=request.user)
    messages.success(request, f"Matching finished: {summary.evaluated} item(s) checked, {summary.gfp} verified, "
                              f"{summary.typo} typo, {summary.manual_review} manual review, {summary.not_found} not found.")
    return redirect("reconciliation:queue")
