"""Variables available in every template."""
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from .models import Notification


def app_context(request):
    start, end = (datetime.strptime(v, "%H:%M").time() for v in settings.BUSINESS_HOURS)
    now = timezone.localtime()
    is_weekday = now.weekday() < 5
    ctx = {
        "APP_NAME": "Payment Reconciliation",
        "BUSINESS_HOURS": settings.BUSINESS_HOURS,
        "within_business_hours": is_weekday and start <= now.time() <= end,
        "REFERENCE_MIN": settings.REFERENCE_MIN_LENGTH,
        "REFERENCE_MAX": settings.REFERENCE_MAX_LENGTH,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_notifications"] = Notification.objects.filter(recipient=user, status="unread").count()
    return ctx
