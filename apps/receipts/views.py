"""Teller screens: submit a receipt (online or queued offline), list receipts, see results."""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
import json

from django.db.models import Case, IntegerField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.permissions import role_required
from apps.reconciliation.models import MatchStatus
from apps.reconciliation.services import review
from apps.reconciliation.services.engine import run_matching
from apps.reconciliation.services.submissions import create_submission

from .forms import ReceiptForm, duplicate_info
from .models import TellerSubmission


def _rejected_first(qs):
    """Rejected receipts are always at the top of the Teller's lists; the rest keeps the newest-first order."""
    return qs.annotate(_rank=Case(When(match__match_status=MatchStatus.REJECTED, then=Value(0)), default=Value(1), output_field=IntegerField())
                       ).order_by("_rank", "-entered_at")


def _wants_json(request) -> bool:
    return "application/json" in request.headers.get("Accept", "")


def _trusted_entered_at(value):
    """
    Offline receipts carry the time the teller typed them. Accept it only when plausible
    (not in the future, not older than OFFLINE_TIMESTAMP_MAX_AGE_DAYS); otherwise use server time.
    """
    now = timezone.now()
    if value and now - timedelta(days=settings.OFFLINE_TIMESTAMP_MAX_AGE_DAYS) <= value <= now + timedelta(minutes=5):
        return value
    return None


@role_required(Role.TELLER)
def new_receipt(request):
    """REQ: Receipt Management. Branch is taken from the signed-in teller, never typed."""
    branch = request.user.branch
    form = ReceiptForm(request.POST or None) if branch else None

    if request.method == "POST" and form is not None:
        if form.is_valid():
            submission, created = create_submission(
                user=request.user, data=form.cleaned_data,
                entered_at=_trusted_entered_at(form.cleaned_data.get("entered_at")))
            if _wants_json(request):
                if created:  # the page reloads after this response, so the message appears there
                    messages.success(request, f"Receipt #{submission.pk} saved. Finance will verify it against the bank statement.")
                return JsonResponse({"ok": True, "id": submission.pk, "created": created}, status=201 if created else 200)
            messages.success(request, f"Receipt #{submission.pk} saved. Finance will verify it against the bank statement.")
            return redirect("receipts:new")
        if _wants_json(request):
            html = render_to_string("receipts/_form.html", {"form": form, "branch": branch}, request=request)
            if form.duplicate:   # already entered (maybe by another branch): the browser shows a red pop-up
                return JsonResponse({"ok": False, "duplicate": form.popup, "html": html}, status=409)
            return JsonResponse({"ok": False, "html": html}, status=400)

    recent = _rejected_first(TellerSubmission.objects.filter(branch=branch).select_related("match", "bank"))[:8] if branch else []
    return render(request, "receipts/new.html", {"form": form, "branch": branch, "recent": recent})


@role_required(Role.TELLER)
def receipt_list(request):
    branch = request.user.branch
    qs = (TellerSubmission.objects.filter(branch=branch).select_related("match", "bank", "submitted_by")
          if branch else TellerSubmission.objects.none())
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    if status == MatchStatus.GFP:
        qs = qs.filter(match__match_status=MatchStatus.GFP)
    elif status == MatchStatus.REJECTED:
        qs = qs.filter(match__match_status=MatchStatus.REJECTED)
    elif status == MatchStatus.PENDING:   # for a teller, "pending" is everything that is neither verified nor rejected
        qs = qs.exclude(match__match_status__in=[MatchStatus.GFP, MatchStatus.REJECTED])
    if q:
        qs = qs.filter(Q(bank_reference_no__icontains=q) | Q(sender_name__icontains=q) | Q(account_holder_name__icontains=q))
    page = Paginator(_rejected_first(qs), 25).get_page(request.GET.get("page"))
    context = {"page": page, "status": status, "q": q,
               "statuses": [(MatchStatus.REJECTED, "Reject"), (MatchStatus.PENDING, "Pending"), (MatchStatus.GFP, "Verified")]}
    if request.headers.get("X-Live-Search"):   # live search: only the part that changes
        return render(request, "receipts/_list_results.html", context)
    return render(request, "receipts/list.html", context)


@role_required(Role.TELLER)
def receipt_detail(request, pk: int):
    sub = get_object_or_404(TellerSubmission.objects.select_related("match", "bank", "branch", "submitted_by"),
                            pk=pk, branch=request.user.branch)
    return render(request, "receipts/detail.html", {"sub": sub, "match": sub.match, "can_edit": sub.match.is_open})


@role_required(Role.TELLER)
def receipt_edit(request, pk: int):
    """Teller fixes a receipt after Finance asked for a correction (REVIEW flow)."""
    sub = get_object_or_404(TellerSubmission.objects.select_related("match", "bank"), pk=pk, branch=request.user.branch)
    match = sub.match
    if not match.is_open:
        messages.error(request, "This receipt is verified and can no longer be edited.")
        return redirect("receipts:detail", pk=pk)
    initial = {"client_uuid": sub.client_uuid, "sender_name": sub.sender_name, "account_holder_name": sub.account_holder_name,
               "relationship": sub.relationship, "bank": sub.bank_id, "amount": f"{sub.amount:.2f}".replace(".", ","),
               "bank_reference_no": sub.bank_reference_no, "payment_method_code": sub.payment_method_code,
               "transaction_at": timezone.localtime(sub.transaction_at).strftime("%Y-%m-%dT%H:%M")}
    form = ReceiptForm(request.POST or None, initial=initial, submission=sub)
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data, client_uuid=sub.client_uuid)   # the identity of the receipt never changes
        try:
            review.correct_submission(match, request.user, data)
        except review.ReviewError as exc:
            messages.error(request, str(exc))
            return redirect("receipts:detail", pk=pk)
        run_matching(actor=request.user, match_ids=[match.pk], quiet=True, promote_only=True)
        match.refresh_from_db()
        messages.success(request, f"Receipt #{sub.pk} corrected. Status: {'Verified' if match.teller_status == 'gfp' else 'Pending'}.")
        return redirect("receipts:detail", pk=pk)
    popup = form.popup if request.method == "POST" else None       # red pop-up: the same data was entered before
    return render(request, "receipts/edit.html", {"form": form, "branch": request.user.branch, "sub": sub, "editing": True,
                                                  "popup_json": json.dumps(popup) if popup else ""})
