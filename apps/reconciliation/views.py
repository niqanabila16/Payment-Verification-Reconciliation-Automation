"""Finance screens: reconciliation table (with the upload box), match detail, upload history, report."""
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from rapidfuzz import fuzz

from apps.accounts.models import Branch, Role
from apps.core.audit import record
from apps.core.models import Bank, TransactionDescription
from apps.core.normalize import normalize_reference
from apps.core.permissions import role_required

from .forms import ReportForm, StatementUploadForm
from .models import MatchStatus, ReconciliationMatch, StatementEntry, StatementImport, entry_from_snapshot
from .services import report as report_service
from .services import review
from .services.engine import _name_required_bank_ids, failed_fields, name_score, names_match, reference_matches
from .services.retention import purge_if_due
from .services.importer import find_previous_upload, read_upload, start_import
from .services.parser import BankMismatchError, Row1UnreadableError, StatementParseError

TABS = [
    ("pending", "Pending", [MatchStatus.PENDING]),
    ("review", "Review", [MatchStatus.MANUAL_REVIEW]),
    ("rejected", "Reject", [MatchStatus.REJECTED]),
    ("not_found", "Not found", [MatchStatus.NOT_FOUND]),
    ("open_item", "Open Item", None),            # bank rows nobody claimed: a different table
    ("verified", "Verified", [MatchStatus.GFP]),
    ("all", "All", None),
]
RECEIPT_STATUSES = {key: statuses for key, _, statuses in TABS if key not in ("open_item",)}


def _safe_next(request, fallback: str = ""):
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def _back(request, pk):
    """After an action: return to the page it was started from (the table), else to the item."""
    target = _safe_next(request)
    return redirect(target) if target else redirect("reconciliation:detail", pk=pk)


def _description_options(bank_id: str) -> list[str]:
    """Options of the "Transaction description" dropdown (managed by Admin in Master data), for the chosen bank or all banks."""
    qs = TransactionDescription.objects.filter(is_active=True)
    if bank_id.isdigit():
        qs = qs.filter(Q(bank_id=int(bank_id)) | Q(bank__isnull=True))
    return list(dict.fromkeys(qs.order_by("name").values_list("name", flat=True)))


def _handle_upload(request, form):
    """
    Process a statement upload posted to the main page.
    Returns (response, extra_context): a redirect on success, otherwise None plus flags for re-rendering.
    """
    extra = {"confirm_next": False, "show_manual": False}
    if not form.is_valid():
        return None, extra
    upload, bank, confirmed = form.cleaned_data["file"], form.cleaned_data["bank"], request.POST.get("confirm_duplicate") == "1"
    try:
        data, digest = read_upload(upload)
        previous = None if confirmed else find_previous_upload(upload.name, digest)
        if previous:
            when = timezone.localtime(previous.imported_at)
            form.add_error("file", f'A file named "{previous.file_name}" was already uploaded on {when:%d %b %Y %H:%M}. '
                                   'Select the file again and press "Upload again" to confirm.')
            extra["confirm_next"] = True
            return None, extra
        imp = start_import(user=request.user, bank=bank, data=data, digest=digest, file_name=upload.name,
                           fallback_account=form.cleaned_data.get("account_number", ""),
                           fallback_date=form.cleaned_data.get("statement_date"))
    except BankMismatchError as exc:
        # The file belongs to another bank than the one selected: keep the page, preselect the right bank.
        right = Bank.objects.filter(statement_format=exc.detected, is_active=True).first()
        if right:
            form.data = form.data.copy()
            form.data["bank"] = str(right.pk)
        form.add_error("file", str(exc))
        return None, extra
    except Row1UnreadableError as exc:
        form.add_error("file", str(exc))
        extra["show_manual"] = True
        return None, extra
    except StatementParseError as exc:
        form.add_error("file", str(exc))
        return None, extra
    return redirect("reconciliation:import_detail", pk=imp.pk), extra


def _open_entries():
    """Bank rows nobody claimed: not finally linked and not waiting as the suggestion of a Review."""
    return StatementEntry.objects.filter(match__isnull=True).exclude(suggested_for__match_status=MatchStatus.MANUAL_REVIEW)


def _closest_rows(match: ReconciliationMatch, limit: int = 3) -> list[dict]:
    """
    For a receipt without any compared bank row (Pending / Not found): the nearest unclaimed rows of the same bank, with the
    result of each field, so Finance can see what is close. They are NOT matches.
    """
    sub = match.teller_submission
    needs_name = sub.bank_id in _name_required_bank_ids()
    rows = (_open_entries().filter(bank_id=sub.bank_id, matchable=True).select_related("statement_import")
            .order_by("-statement_import__imported_at", "-id")[:500])
    found = []
    for entry in rows:
        failed = failed_fields(sub, entry, needs_name)
        if len(failed) >= 2:
            continue
        ref_score = fuzz.ratio(sub.reference_normalized, entry.reference_normalized)
        found.append({"entry": entry, "failed": sorted(failed), "ref_score": ref_score,
                      "amount_diff": abs(entry.amount - sub.amount) if entry.amount != sub.amount else None,
                      "score": (3 - len(failed)) * 100 + ref_score})
    return sorted(found, key=lambda c: -c["score"])[:limit]


@role_required(Role.FINANCE, Role.ADMIN)
def queue(request):
    """Receipts by status (newest first) or the Open Item list. Finance also uploads the bank statement here."""
    upload_form, extra = None, {"confirm_next": False, "show_manual": False}
    if request.user.role == Role.FINANCE:
        upload_form = StatementUploadForm(request.POST or None, request.FILES or None)
        if request.method == "POST":
            response, extra = _handle_upload(request, upload_form)
            if response:
                return response
    elif request.method == "POST":
        raise PermissionDenied
    purge_if_due()                            # bank data older than 31 days is deleted (at most once an hour)

    q = request.GET.get("q", "").strip()
    description = request.GET.get("description", "").strip()
    bank = request.GET.get("bank", "")
    branch = request.GET.get("branch", "")
    normalized_q = normalize_reference(q)

    receipts = ReconciliationMatch.objects.select_related(
        "teller_submission", "teller_submission__branch", "teller_submission__bank", "teller_submission__submitted_by",
        "suggested_bank_statement_entry")
    entries = _open_entries().select_related("bank", "statement_import")
    if description:
        entries = entries.filter(description__iexact=description)
    if q:
        receipts = receipts.filter(Q(teller_submission__bank_reference_no__icontains=q)
                                   | (Q(teller_submission__reference_normalized__icontains=normalized_q) if normalized_q else Q(pk__in=[]))
                                   | Q(teller_submission__sender_name__icontains=q) | Q(teller_submission__account_holder_name__icontains=q))
        entries = entries.filter(Q(reference__icontains=q) | Q(counterparty_name__icontains=q) | Q(description__icontains=q)
                                 | (Q(reference_normalized__icontains=normalized_q) if normalized_q else Q(pk__in=[])))
    if bank.isdigit():
        receipts = receipts.filter(teller_submission__bank_id=int(bank))
        entries = entries.filter(bank_id=int(bank))
    if branch.isdigit():                      # branches exist only on receipts
        receipts = receipts.filter(teller_submission__branch_id=int(branch))

    counts = receipts.aggregate(**{key: Count("id", filter=Q(match_status__in=statuses) if statuses else None)
                                   for key, statuses in RECEIPT_STATUSES.items()})
    counts["open_item"] = entries.count()
    tab = request.GET.get("tab", "")
    if tab not in {key for key, _, _ in TABS}:  # no tab chosen: open the first list that needs work, else everything
        tab = next((k for k in ("review", "rejected", "not_found", "open_item", "pending") if counts[k]), "all")

    if tab == "open_item":
        page = Paginator(entries.order_by("-statement_import__imported_at", "source_row", "id"), 25).get_page(request.GET.get("page"))
    else:
        statuses = RECEIPT_STATUSES[tab]
        qs = receipts.filter(match_status__in=statuses) if statuses else receipts
        page = Paginator(qs.order_by("-status_changed_at", "-id"), 25).get_page(request.GET.get("page"))
        for m in page.object_list:      # the compared bank row (Review: suggestion, Reject: the rejected row)
            entry, sub = m.suggested_bank_statement_entry or m.rejected_bank_statement_entry, m.teller_submission
            m.review_entry = entry
            m.review_ref = entry.reference_normalized if entry else ""
            m.amount_diff = abs(entry.amount - sub.amount) if entry and entry.amount != sub.amount else None

    context = {
        "page": page, "tab": tab, "tabs": [(k, label, counts[k]) for k, label, _ in TABS],
        "q": q, "bank": bank, "branch": branch, "banks": Bank.objects.exclude(statement_format=""), "branches": Branch.objects.all(),
        "description": description, "descriptions": _description_options(bank),
        "upload_form": upload_form, "report_form": ReportForm() if request.user.role == Role.FINANCE else None,
        "can_decide": request.user.role == Role.FINANCE, **extra,
    }
    if request.headers.get("X-Live-Search"):          # live search: only the part that changes
        return render(request, "reconciliation/_queue_results.html", context)
    context["known_files_json"] = json.dumps(
        [n.lower() for n in StatementImport.objects.order_by("-imported_at").values_list("file_name", flat=True)[:300]])
    return render(request, "reconciliation/queue.html", context)


# --------------------------------------------------------------------------
# Detail: side-by-side comparison (identical = green, different = red) and the decision box (Note + GFP + Reject)
# --------------------------------------------------------------------------
def _compared_entry(match: ReconciliationMatch):
    """(entry, kind): the bank row shown in the comparison. A verified receipt whose bank row was purged uses its snapshot."""
    if match.bank_statement_entry_id:
        return match.bank_statement_entry, "Matched bank row"
    if match.match_status == MatchStatus.GFP and match.bank_snapshot:
        return entry_from_snapshot(match.bank_snapshot), "Matched bank row (kept after the bank data was deleted)"
    if match.suggested_bank_statement_entry_id:
        return match.suggested_bank_statement_entry, "Suggested bank row"
    if match.rejected_bank_statement_entry_id:
        return match.rejected_bank_statement_entry, "Rejected bank row"
    return None, ""


def _comparison(match: ReconciliationMatch, entry):
    """Build the rows of the side-by-side table. state: 'same' | 'diff' | 'info'."""
    sub = match.teller_submission
    needs_name = sub.bank_id in _name_required_bank_ids()
    bank_ref = entry.reference_normalized
    # The reference is not always a matching key, but a difference is still shown in red (like a typo in the name).
    ref_state = ("same" if reference_matches(sub.reference_normalized, bank_ref) else "diff") if bank_ref else "info"
    amount_state = "same" if entry.amount == sub.amount else "diff"
    if needs_name or entry.counterparty_name:
        name_ok = names_match(sub, entry)
        name_row = {"label": "Name", "kind": "text", "teller": sub.account_holder_name, "bank": entry.counterparty_name or "-",
                    "state": "same" if name_ok else ("diff" if needs_name else "info"),
                    "hint": None if name_ok else "The bank name is compared with the Teller's account holder (any word order; at least two words in common)."}
    else:
        name_row = {"label": "Name", "kind": "text", "teller": sub.account_holder_name, "bank": "-", "state": "info", "hint": "This bank does not print a name."}
    rows = [
        {"label": "Reference", "kind": "reference", "teller": sub.reference_normalized, "bank": bank_ref,
         "teller_raw": sub.bank_reference_no, "bank_raw": entry.display_reference, "state": ref_state,
         "hint": None},
        {"label": "Amount", "kind": "amount", "teller": sub.amount, "bank": entry.amount, "state": amount_state,
         "hint": None if amount_state == "same" else f"Difference: RM {abs(entry.amount - sub.amount):,.2f}"},
        name_row,
        {"label": "Date", "kind": "text", "teller": f"{timezone.localtime(sub.transaction_at):%d %b %Y %H:%M}",
         "bank": f"{entry.display_date:%d %b %Y}" if entry.display_date else "-", "state": "info"},
        {"label": "Method / description", "kind": "text", "teller": sub.payment_method_label, "bank": entry.description or "-", "state": "info"},
    ]
    return rows


@role_required(Role.FINANCE, Role.ADMIN)
def detail(request, pk: int):
    match = get_object_or_404(ReconciliationMatch.objects.select_related(
        "teller_submission", "teller_submission__branch", "teller_submission__bank", "teller_submission__submitted_by",
        "bank_statement_entry", "bank_statement_entry__statement_import", "suggested_bank_statement_entry",
        "suggested_bank_statement_entry__statement_import", "rejected_bank_statement_entry",
        "rejected_bank_statement_entry__statement_import", "matched_by"), pk=pk)
    entry, entry_kind = _compared_entry(match)
    rows = _comparison(match, entry) if entry is not None else None
    can_act = request.user.role == Role.FINANCE
    status = match.match_status
    return render(request, "reconciliation/detail.html", {
        "match": match, "sub": match.teller_submission, "entry": entry, "entry_kind": entry_kind, "rows": rows,
        "has_diff": bool(rows) and any(r["state"] == "diff" for r in rows),
        "amount_differs": entry is not None and entry.amount != match.teller_submission.amount,
        "closest": _closest_rows(match) if entry is None and status in (MatchStatus.NOT_FOUND, MatchStatus.PENDING) else [],
        "can_act": can_act,
        "can_gfp": can_act and entry is not None and status in (MatchStatus.MANUAL_REVIEW, MatchStatus.REJECTED),
        "can_reject": can_act and status not in (MatchStatus.GFP, MatchStatus.REJECTED),
        "reject_reasons": review.REJECT_REASONS,
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
    return _back(request, pk)


@role_required(Role.FINANCE)
@require_POST
def reject(request, pk: int):
    if _act(request, pk, lambda m: review.reject_receipt(m, request.user, request.POST.get("reject_reason", ""), request.POST.get("note", ""))):
        messages.success(request, "Rejected. The teller sees status Reject with your reason and must correct the receipt.")
    return _back(request, pk)


# --------------------------------------------------------------------------
# Report, upload history and import result
# --------------------------------------------------------------------------
@role_required(Role.FINANCE)
@require_GET
def report(request):
    """Excel report of the bank transactions of a week or a month with their status (GFP / Open Item)."""
    form = ReportForm(request.GET)
    if not form.is_valid():
        messages.error(request, "Choose weekly or monthly and a valid date for the report.")
        return redirect("reconciliation:queue")
    bank = form.cleaned_data["bank"]
    content, filename = report_service.build_report(form.cleaned_data["period"], form.cleaned_data["date"], bank.pk if bank else None,
                                                    form.cleaned_data.get("description", ""))
    record("report", 0, "report.generated", actor=request.user, file=filename)
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@role_required(Role.FINANCE)
def import_list(request):
    page = Paginator(StatementImport.objects.select_related("uploaded_by", "bank"), 20).get_page(request.GET.get("page"))
    return render(request, "reconciliation/import_list.html", {"page": page})


@role_required(Role.FINANCE, Role.ADMIN)
def import_detail(request, pk: int):
    imp = get_object_or_404(StatementImport.objects.select_related("uploaded_by", "bank"), pk=pk)
    summary = imp.result_summary or {}
    return render(request, "reconciliation/import_detail.html", {
        "imp": imp, "summary": summary,
        "review_count": summary.get("manual_review", 0),
    })


@role_required(Role.FINANCE, Role.ADMIN)
@require_GET
def import_status(request, pk: int):
    """Polled by the progress bar."""
    imp = get_object_or_404(StatementImport, pk=pk)
    return JsonResponse({"status": imp.status, "progress": imp.progress_percent, "error": imp.error_message})