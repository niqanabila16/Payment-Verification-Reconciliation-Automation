"""Variables available in every template."""
from django.conf import settings

from .models import Notification


def app_context(request):
    ctx = {
        "APP_NAME": "Payment Reconciliation",
        "REFERENCE_MIN": settings.REFERENCE_MIN_LENGTH,
        "REFERENCE_MAX": settings.REFERENCE_MAX_LENGTH,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        ctx["unread_notifications"] = Notification.objects.filter(recipient=user, status="unread").count()
    return ctx
