"""Finance screens: reconciliation queue (with the upload box), match detail, upload history."""
import json


from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from rapidfuzz import fuzz

from apps.accounts.models import Branch, Role
from apps.core.permissions import role_required

from .forms import ReassignForm, StatementUploadForm
from .models import MatchStatus, ReconciliationMatch, StatementImport
from .services import review
from .services.importer import find_previous_upload, read_upload, start_import
from .services.parser import Row1UnreadableError, StatementParseError

TABS = [
    ("pending", "Pending", [MatchStatus.PENDING]),
    ("review", "Review", [MatchStatus.TYPO, MatchStatus.MANUAL_REVIEW]),
    ("not_found", "Not found", [MatchStatus.NOT_FOUND]),
    ("verified", "Verified", [MatchStatus.GFP]),
    ("all", "All", None),
]


def _handle_upload(request, form):
    """
    Process a statement upload posted to the queue page.
    Returns (response, extra_context): a redirect on success, otherwise None plus flags for re-rendering.
    """
    extra = {"confirm_next": False, "show_manual": False}
    if not form.is_valid():
        return None, extra
    upload, confirmed = form.cleaned_data["file"], request.POST.get("confirm_duplicate") == "1"
    try:
        data, digest = read_upload(upload)
        previous = None if confirmed else find_previous_upload(upload.name, digest)
        if previous:
            when = timezone.localtime(previous.imported_at)
            form.add_error("file", f'A file named "{previous.file_name}" was already uploaded on {when:%d %b %Y %H:%M}. '
                                   'Select the file again and press "Upload again" to confirm.')
            extra["confirm_next"] = True
            return None, extra
        imp = start_import(user=request.user, data=data, digest=digest, file_name=upload.name,
                           fallback_account=form.cleaned_data.get("account_number", ""),
                           fallback_date=form.cleaned_data.get("statement_date"))
    except Row1UnreadableError as exc:
        form.add_error("file", str(exc))
        extra["show_manual"] = True
        return None, extra
    except StatementParseError as exc:
        form.add_error("file", str(exc))
        return None, extra
    return redirect("reconciliation:import_detail", pk=imp.pk), extra


@role_required(Role.FINANCE, Role.ADMIN)
def queue(request):
    """Queue of receipts by status, oldest first. Finance also uploads the bank statement here."""
    upload_form, extra = None, {"confirm_next": False, "show_manual": False}
    if request.user.role == Role.FINANCE:
        upload_form = StatementUploadForm(request.POST or None, request.FILES or None)
        if request.method == "POST":
            response, extra = _handle_upload(request, upload_form)
            if response:
                return response
    elif request.method == "POST":
        raise PermissionDenied

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

    # One query gives the counts for every tab.
    counts = base.aggregate(**{key: Count("id", filter=Q(match_status__in=statuses) if statuses else None)
                               for key, _, statuses in TABS})
    tab_map = {key: statuses for key, _, statuses in TABS}
    tab = request.GET.get("tab", "")
    if tab not in tab_map:  # no tab chosen: open the first list that needs work, else everything
        tab = next((k for k in ("review", "not_found", "pending") if counts[k]), "all")
    qs = base.filter(match_status__in=tab_map[tab]) if tab_map[tab] else base
    page = Paginator(qs.order_by("first_seen_at", "id"), 20).get_page(request.GET.get("page"))

    known_files = list(StatementImport.objects.order_by("-imported_at").values_list("file_name", flat=True)[:300])
    return render(request, "reconciliation/queue.html", {
        "page": page, "tab": tab, "tabs": [(k, label, counts[k]) for k, label, _ in TABS],
        "q": q, "branch": branch, "branches": Branch.objects.all(),
        "upload_form": upload_form, "known_files_json": json.dumps([n.lower() for n in known_files]), **extra,
    })


# --------------------------------------------------------------------------
# Detail: side-by-side comparison (identical = green, different = red)
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
         "state": "info", "hint": f"{name_score:.0f}% similar"},
        {"label": "Date", "kind": "text", "teller": f"{timezone.localtime(sub.entered_at):%d %b %Y}",
         "bank": f"{entry.statement_import.statement_date:%d %b %Y}", "state": "info"},
        {"label": "Method / description", "kind": "text", "teller": sub.payment_method_label,
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
    return render(request, "reconciliation/detail.html", {
        "match": match, "sub": match.teller_submission, "entry": entry, "rows": rows,
        "has_diff": bool(rows) and any(r["state"] == "diff" for r in rows),
        "reassign_form": ReassignForm(), "can_act": request.user.role == Role.FINANCE,
    })


def _act(request, pk, action) -> bool:
    """Run a review service function; show its error message if a rule blocks it."""
    match = get_object_or_404(ReconciliationMatch, pk=pk)
    try:
        action(match)
    except review.ReviewError as exc:
        messages.error(request, str(exc))
        return False
    return True


@role_required(Role.FINANCE)
@require_POST
def confirm(request, pk: int):
    if _act(request, pk, lambda m: review.confirm_suggestion(m, request.user, request.POST.get("note", ""))):
        messages.success(request, "Approved. The receipt is now verified (GFP).")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def reject(request, pk: int):
    if _act(request, pk, lambda m: review.reject_suggestion(m, request.user, request.POST.get("note", ""))):
        messages.success(request, "Suggestion rejected. The receipt is back in Not found.")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def feedback(request, pk: int):
    if _act(request, pk, lambda m: review.send_feedback(m, request.user, request.POST.get("message", ""))):
        messages.success(request, "Feedback sent to the teller.")
    return redirect("reconciliation:detail", pk=pk)


@role_required(Role.FINANCE)
@require_POST
def reassign(request, pk: int):
    form = ReassignForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Select the branch the receipt should be moved to.")
        return redirect("reconciliation:detail", pk=pk)
    if _act(request, pk, lambda m: review.reassign_branch(m, request.user, form.cleaned_data["branch"])):
        messages.success(request, f"Receipt moved to branch {form.cleaned_data['branch'].code}.")
    return redirect("reconciliation:detail", pk=pk)


# --------------------------------------------------------------------------
# Upload history and import result
# --------------------------------------------------------------------------
@role_required(Role.FINANCE)
def import_list(request):
    page = Paginator(StatementImport.objects.select_related("uploaded_by"), 20).get_page(request.GET.get("page"))
    return render(request, "reconciliation/import_list.html", {"page": page})


@role_required(Role.FINANCE, Role.ADMIN)
def import_detail(request, pk: int):
    imp = get_object_or_404(StatementImport.objects.select_related("uploaded_by"), pk=pk)
    summary = imp.result_summary or {}
    return render(request, "reconciliation/import_detail.html", {
        "imp": imp, "summary": summary,
        "review_count": summary.get("typo", 0) + summary.get("manual_review", 0),
    })


@role_required(Role.FINANCE, Role.ADMIN)
@require_GET
def import_status(request, pk: int):
    """Polled by the progress bar."""
    imp = get_object_or_404(StatementImport, pk=pk)
    return JsonResponse({"status": imp.status, "progress": imp.progress_percent, "error": imp.error_message})
