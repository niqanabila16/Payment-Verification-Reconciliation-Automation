"""
Notification service (BR-7).

Delivery channels:
  1. In-app: stored in the Notification table, shown by the bell icon.
  2. Browser notifications: the page polls the unread endpoint and raises a desktop notification
     (works while the site is open in any tab/window, even in the background).
  3. E-mail digest (optional, NOTIFY_BY_EMAIL=True): reaches users who closed the website entirely.
"""
import logging
from collections.abc import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .models import Notification

logger = logging.getLogger(__name__)


def notify_users(users: Iterable, type: str, message: str, entity_type: str = "", entity_id: int | None = None):
    """Create one in-app notification per user (each user tracks their own read state)."""
    rows = [
        Notification(recipient=user, recipient_role=user.role, type=type, message=message,
                     related_entity_type=entity_type, related_entity_id=entity_id)
        for user in users
    ]
    return Notification.objects.bulk_create(rows)


def notify_role(role: str, type: str, message: str, entity_type: str = "", entity_id: int | None = None):
    """Broadcast to every active user with `role` (e.g. all Finance staff)."""
    from apps.accounts.models import User

    return notify_users(User.objects.filter(role=role, is_active=True), type, message, entity_type, entity_id)


def _role(notification: Notification) -> str:
    return notification.recipient.role if notification.recipient_id else notification.recipient_role


def notification_url(notification: Notification) -> str:
    """Where clicking a notification should lead."""
    kind, pk = notification.related_entity_type, notification.related_entity_id
    try:
        if kind == "match" and pk:
            return reverse("reconciliation:detail", args=[pk])
        if kind == "submission" and pk:
            return reverse("receipts:detail", args=[pk])
        if kind == "cards":
            return reverse("cards:teller_cards") if _role(notification) == "teller" else reverse("cards:cs_cards")
        if kind == "activation":
            return reverse("cards:teller_requests") if _role(notification) == "teller" else reverse("cards:cs_requests")
        if kind == "import" and pk:
            return reverse("reconciliation:import_detail", args=[pk])
    except Exception:  # pragma: no cover - a dangling reference must never break the page
        logger.exception("Could not build notification URL")
    return reverse("core:notifications")


def send_digest_email(user, subject: str, lines: list[str]) -> bool:
    """Send one summary e-mail (only when NOTIFY_BY_EMAIL is on and the user has an address)."""
    if not settings.NOTIFY_BY_EMAIL or not user.email or not lines:
        return False
    body = "Hello " + user.name + ",\n\n" + "\n".join(f"- {line}" for line in lines) + \
           "\n\nOpen the Payment Reconciliation website to see the details."
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return True
    except Exception:  # SMTP down must never break reconciliation
        logger.exception("E-mail digest to %s failed", user.email)
        return False
