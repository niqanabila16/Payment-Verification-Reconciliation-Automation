"""Teller screens: submit a receipt (online or queued offline), list receipts, see results."""
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.permissions import role_required
from apps.reconciliation.forms import CommentForm
from apps.reconciliation.models import MatchStatus, ReconciliationMatch
from apps.reconciliation.services import review
from apps.reconciliation.services.engine import run_matching
from apps.reconciliation.services.submissions import create_submission

from .forms import ReceiptForm
from .models import TellerSubmission


def _wants_json(request) -> bool:
    return "application/json" in request.headers.get("Accept", "")


def _trusted_entered_at(value):
    """
    Offline receipts carry the time the teller typed them. Accept it only when plausible
    (not in the future, not older than the re-check window); otherwise use server time.
    """
    now = timezone.now()
    if value and now - timedelta(days=31) <= value <= now + timedelta(minutes=5):
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
            return JsonResponse({"ok": False, "html": html}, status=400)

    recent = TellerSubmission.objects.filter(branch=branch).select_related("match", "bank")[:8] if branch else []
    return render(request, "receipts/new.html", {"form": form, "branch": branch, "recent": recent})


@role_required(Role.TELLER)
def receipt_list(request):
    branch = request.user.branch
    qs = (TellerSubmission.objects.filter(branch=branch).select_related("match", "bank", "submitted_by")
          if branch else TellerSubmission.objects.none())
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    if status in MatchStatus.values:
        qs = qs.filter(match__match_status=status)
    if q:
        qs = qs.filter(Q(bank_reference_no__icontains=q) | Q(sender_name__icontains=q) | Q(account_holder_name__icontains=q))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "receipts/list.html", {"page": page, "status": status, "q": q, "statuses": MatchStatus.choices})


@role_required(Role.TELLER)
def receipt_detail(request, pk: int):
    sub = get_object_or_404(TellerSubmission.objects.select_related("match", "bank", "branch", "submitted_by"),
                            pk=pk, branch=request.user.branch)
    match: ReconciliationMatch = sub.match
    return render(request, "receipts/detail.html", {
        "sub": sub, "match": match, "comments": match.comments.select_related("author"),
        "comment_form": CommentForm(), "can_edit": match.match_status in review.EDITABLE_STATUSES,
    })


@role_required(Role.TELLER)
def receipt_edit(request, pk: int):
    """Teller fixes a receipt after Finance asked for a correction (REVIEW flow)."""
    sub = get_object_or_404(TellerSubmission.objects.select_related("match", "bank"), pk=pk, branch=request.user.branch)
    match = sub.match
    if match.match_status not in review.EDITABLE_STATUSES:
        messages.error(request, "This receipt can no longer be edited because it is verified, closed or still pending.")
        return redirect("receipts:detail", pk=pk)
    initial = {"client_uuid": sub.client_uuid, "sender_name": sub.sender_name, "account_holder_name": sub.account_holder_name,
               "relationship": sub.relationship, "bank": sub.bank_id, "amount": sub.amount,
               "bank_reference_no": sub.bank_reference_no, "payment_method_code": sub.payment_method_code}
    form = ReceiptForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data, client_uuid=sub.client_uuid)   # the identity of the receipt never changes
        try:
            review.correct_submission(match, request.user, data)
        except review.ReviewError as exc:
            messages.error(request, str(exc))
            return redirect("receipts:detail", pk=pk)
        run_matching(actor=request.user, match_ids=[match.pk], quiet=True)
        match.refresh_from_db()
        messages.success(request, f"Receipt #{sub.pk} corrected and re-checked. New status: {match.get_match_status_display()}.")
        return redirect("receipts:detail", pk=pk)
    return render(request, "receipts/edit.html", {"form": form, "branch": request.user.branch, "sub": sub, "editing": True})
