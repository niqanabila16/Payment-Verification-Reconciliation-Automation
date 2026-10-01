"""Cross-cutting pages: home redirect, notifications, architecture page, service worker, health check."""
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .models import Notification
from .notifications import notification_url


@login_required
def home(request):
    """Send each role to its own starting page."""
    return redirect(request.user.landing_url_name)


def permission_denied(request, exception=None):
    """Friendly 403 page (role not allowed to see this page)."""
    return render(request, "403.html", status=403)


@require_GET
def healthz(request):
    """Used by uptime checks / Docker health checks."""
    return JsonResponse({"status": "ok"})


@require_GET
def service_worker(request):
    """
    Serve the service worker from the site root so its scope covers the whole site.
    It caches static files and the Teller form so receipts can be captured while the central
    computer is off (the form then queues receipts locally and syncs later).
    """
    path = Path(settings.BASE_DIR) / "static" / "js" / "sw.js"
    if not path.exists():
        raise Http404
    response = FileResponse(open(path, "rb"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@login_required
def architecture(request):
    return render(request, "core/architecture.html")


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------
@login_required
def notification_list(request):
    qs = Notification.objects.filter(recipient=request.user)
    if request.GET.get("filter") == "unread":
        qs = qs.filter(status="unread")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    for item in page.object_list:
        item.url = notification_url(item)
    return render(request, "core/notifications.html", {"page": page, "filter": request.GET.get("filter", "all")})


@login_required
@require_GET
def notification_poll(request):
    """
    Polled every ~20 s by the page. Returns the unread count plus notifications newer than `after`
    so the browser can raise a desktop notification for each new one.
    """
    try:
        after = int(request.GET.get("after", 0))
    except ValueError:
        after = 0
    mine = Notification.objects.filter(recipient=request.user)
    fresh = mine.filter(id__gt=after, status="unread").order_by("id")[:10]
    return JsonResponse({
        "unread": mine.filter(status="unread").count(),
        "latest_id": mine.order_by("-id").values_list("id", flat=True).first() or 0,
        "items": [{"id": n.id, "message": n.message, "url": notification_url(n)} for n in fresh],
    })


@login_required
@require_POST
def notification_read(request, pk: int):
    Notification.objects.filter(pk=pk, recipient=request.user, status="unread").update(
        status="read", read_at=timezone.now())
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("core:notifications")


@login_required
@require_POST
def notification_read_all(request):
    updated = Notification.objects.filter(recipient=request.user, status="unread").update(
        status="read", read_at=timezone.now())
    messages.success(request, f"Marked {updated} notification(s) as read.")
    return redirect("core:notifications")
