"""Card screens for Customer service (CS) and Tellers: dashboard, cards, requests, blocked cards, report."""
import os

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import CsPerm, Role
from apps.core.permissions import cs_permission_required, role_required

from . import reports
from .forms import BlockForm, CardFileForm, CardRequestForm, DeliverForm, StatusForm
from .models import CARD_STATUS_BY_SLUG, RESUBMITTABLE, ActivationRequest, Card, CardStatus, RequestStatus
from .services import (CardError, accept_cards, block_cards, dashboard, deliver_cards, import_card_file, resubmit_request, submit_request, suggest_cards,
                       update_request_status)

PAGE_SIZE = 50
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CS_TABS = (CardStatus.NOT_SENT, CardStatus.DELIVERED, CardStatus.ACCEPTED, CardStatus.COLLECTED, CardStatus.BLOCKED)
TELLER_TABS = (CardStatus.DELIVERED, CardStatus.ACCEPTED, CardStatus.BLOCKED)


def _ids(request) -> list[int]:
    return [int(v) for v in request.POST.getlist("card") if v.isdigit()]


def _back(request, default: str):
    target = request.POST.get("next") or ""
    return redirect(target if target.startswith("/") and not target.startswith("//") else default)


# ---------------------------------------------------------------- dashboard (JSON for the live refresh) and report
@role_required(Role.TELLER, Role.CS, Role.ADMIN)
@require_GET
def dashboard_data(request):
    """The dashboard numbers as JSON. The pages ask for them every few seconds, so a delivery, a block or a new card request shows up by itself."""
    response = JsonResponse(dashboard(request.user))
    response["Cache-Control"] = "no-store"
    return response


@role_required(Role.TELLER, Role.CS, Role.ADMIN)
@require_GET
def dashboard_page(request):
    """The card dashboard: its own page in the header menu."""
    return render(request, "cards/dashboard.html", {"dash": dashboard(request.user)})


@role_required(Role.TELLER, Role.CS, Role.ADMIN)
@require_GET
def report(request):
    """Excel report: Teller = the own branch ("Card - <Branch>"), CS and Admin = head office ("Card Monitoring - HQ")."""
    if request.user.role == Role.TELLER:
        data, name = reports.teller_report(request.user)
    else:
        data, name = reports.cs_report(request.user)
    response = HttpResponse(data, content_type=XLSX)
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    response["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------- CS: cards
@role_required(Role.CS, Role.ADMIN)
def cs_cards(request):
    tab = CARD_STATUS_BY_SLUG.get(request.GET.get("tab", ""), CardStatus.NOT_SENT)
    if tab not in CS_TABS:
        tab = CardStatus.NOT_SENT
    counts = dict(Card.objects.order_by().values_list("status").annotate(n=Count("id")))
    tabs = [(s.slug, s.label, counts.get(s, 0)) for s in CS_TABS]
    qs = Card.objects.filter(status=tab).select_related("branch", "block")
    branch = request.GET.get("branch", "")
    if tab != CardStatus.NOT_SENT and branch.isdigit():
        qs = qs.filter(branch_id=branch)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(card_no__icontains=q)
    page = Paginator(qs.order_by("upload_id", "position", "id"), PAGE_SIZE).get_page(request.GET.get("page"))
    user = request.user
    can_batch, can_block = user.can_cs(CsPerm.BATCH), user.can_cs(CsPerm.BLOCK)
    return render(request, "cards/cs_cards.html", {
        "tab": tab.slug, "tabs": tabs, "page": page, "q": q, "branch": branch,
        "can_batch": can_batch, "can_block": can_block,
        "selectable": (can_batch and tab == CardStatus.NOT_SENT) or (can_block and tab in (CardStatus.DELIVERED, CardStatus.ACCEPTED)),
        "form_id": "deliver-form" if tab == CardStatus.NOT_SENT else "block-form",
        "upload_form": CardFileForm() if can_batch else None, "block_form": BlockForm() if can_block else None,
        "deliver_branches": DeliverForm().fields["branch"].queryset,
    })


@cs_permission_required(CsPerm.BATCH)
@require_POST
def cs_upload(request):
    form = CardFileForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose a card file first.")
        return redirect("cards:cs_cards")
    upload = form.cleaned_data["file"]
    try:
        result = import_card_file(request.user, upload.read(), upload.name)
    except CardError as exc:
        messages.error(request, str(exc))
        return redirect("cards:cs_cards")
    extra = []
    if result["already_stored"]:
        extra.append(f'{result["already_stored"]} already stored')
    if result["repeated"]:
        extra.append(f'{result["repeated"]} repeated in the file')
    messages.success(request, f'{result["added"]} card number(s) added as Not Sent.' + (f' Skipped: {", ".join(extra)}.' if extra else ""))
    return redirect("cards:cs_cards")


@cs_permission_required(CsPerm.BATCH)
@require_POST
def cs_deliver(request):
    form = DeliverForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose the destination branch.")
        return redirect("cards:cs_cards")
    try:
        count = deliver_cards(request.user, _ids(request), form.cleaned_data["branch"])
    except CardError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'{count} card(s) delivered to {form.cleaned_data["branch"].code}.')
    return redirect("cards:cs_cards")


@cs_permission_required(CsPerm.BLOCK)
@require_POST
def cs_block(request):
    form = BlockForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Write the reason for blocking the card(s).")
        return _back(request, "cards:cs_cards")
    try:
        count = block_cards(request.user, _ids(request), form.cleaned_data["note"])
    except CardError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{count} card(s) blocked.")
    return _back(request, "cards:cs_cards")


# ---------------------------------------------------------------- CS: activation requests
@role_required(Role.CS, Role.ADMIN)
def cs_requests(request):
    status = request.GET.get("status", "")
    counts = dict(ActivationRequest.objects.order_by().values_list("status").annotate(n=Count("id")))
    tabs = [("", "All", sum(counts.values()))] + [(str(v), label, counts.get(v, 0)) for v, label in RequestStatus.choices]
    qs = ActivationRequest.objects.select_related("branch", "submitted_by", "card")
    if status.isdigit() and int(status) in RequestStatus.values:
        qs = qs.filter(status=int(status))
    else:
        status = ""
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(customer_name__icontains=q) | Q(file_name__icontains=q) | Q(card__card_no__icontains=q))
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "cards/cs_requests.html", {
        "tabs": tabs, "status": status, "page": page, "q": q,
        "can_manage": request.user.can_cs(CsPerm.ACTIVATION), "status_form": StatusForm()})


@cs_permission_required(CsPerm.ACTIVATION)
@require_POST
def cs_request_status(request, pk):
    form = StatusForm(request.POST)
    if form.is_valid():
        try:
            req = update_request_status(request.user, pk, form.cleaned_data["status"], form.cleaned_data["follow_up"], form.cleaned_data["reject_reason"])
            messages.success(request, f'"{req.customer_name or req.file_name}" is now {req.get_status_display()}.')
        except CardError as exc:
            messages.error(request, str(exc))
        except ActivationRequest.DoesNotExist:
            raise Http404
    else:
        messages.error(request, "Choose a valid status.")
    return _back(request, "cards:cs_requests")


# ---------------------------------------------------------------- Teller
def _requests_page(request, form):
    page = Paginator(ActivationRequest.objects.filter(branch=request.user.branch).select_related("submitted_by", "card"), PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "cards/teller_requests.html", {"page": page, "form": form, "resubmittable": RESUBMITTABLE,
                                                          "suggest_url": "cards:card_suggest"})


@role_required(Role.TELLER)
def teller_requests(request):
    return _requests_page(request, CardRequestForm())


@role_required(Role.TELLER)
@require_POST
def teller_submit(request):
    form = CardRequestForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            req = submit_request(request.user, form.cleaned_data, form.cleaned_data["file"], form.full_card_no())
        except CardError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f'Card {req.card.card_no} for {req.customer_name} was sent to Customer service.')
            return redirect("cards:teller_requests")
    response = _requests_page(request, form)
    response.status_code = 422
    return response


@role_required(Role.TELLER)
@require_GET
def card_suggest(request):
    """Search-as-you-type for the Card No field: card numbers of the own branch that are still free, most similar first."""
    typed = request.GET.get("q", "")
    numbers = suggest_cards(request.user, typed)
    bin_ = settings.CARD_BIN
    response = JsonResponse({"bin": bin_, "suggestions": [n[len(bin_):] for n in numbers]})
    response["Cache-Control"] = "no-store"
    return response


@role_required(Role.TELLER)
@require_POST
def teller_resubmit(request, pk):
    uploaded = request.FILES.get("file")
    try:
        if uploaded is None:
            raise CardError("Choose the corrected PDF file.")
        req = resubmit_request(request.user, pk, uploaded)
    except ActivationRequest.DoesNotExist:
        raise Http404
    except CardError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'"{req.customer_name or req.file_name}" was sent again.')
    return redirect("cards:teller_requests")


@role_required(Role.TELLER)
def teller_cards(request):
    tab = CARD_STATUS_BY_SLUG.get(request.GET.get("tab", ""), CardStatus.DELIVERED)
    if tab not in TELLER_TABS:
        tab = CardStatus.DELIVERED
    base = Card.objects.filter(branch=request.user.branch)
    counts = dict(base.order_by().values_list("status").annotate(n=Count("id")))
    tabs = [(s.slug, s.label, counts.get(s, 0)) for s in TELLER_TABS]
    qs = base.filter(status=tab).select_related("block").order_by("upload_id", "position", "id")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(card_no__icontains=q)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "cards/teller_cards.html", {"tab": tab.slug, "tabs": tabs, "page": page, "q": q})


@role_required(Role.TELLER)
@require_POST
def teller_accept(request):
    try:
        count = accept_cards(request.user, _ids(request))
    except CardError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{count} card(s) accepted.")
    return redirect("cards:teller_cards")


# ---------------------------------------------------------------- PDF
@role_required(Role.TELLER, Role.CS, Role.ADMIN)
@xframe_options_sameorigin
def request_file(request, pk):
    req = get_object_or_404(ActivationRequest, pk=pk)
    if request.user.role == Role.TELLER and req.branch_id != request.user.branch_id:
        raise PermissionDenied
    try:
        handle = req.file.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("The file is no longer available.")
    response = FileResponse(handle, content_type="application/pdf")
    name = os.path.basename(req.file_name).replace('"', "")
    response["Content-Disposition"] = f'inline; filename="{name}"'
    response["Content-Security-Policy"] = "frame-ancestors 'self'; sandbox"
    response["X-Content-Type-Options"] = "nosniff"
    return response
