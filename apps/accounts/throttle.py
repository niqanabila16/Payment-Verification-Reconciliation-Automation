"""
Sign-in throttling: after LOGIN_MAX_ATTEMPTS failures for one e-mail the account is
locked for LOGIN_LOCKOUT_MINUTES. Uses Django's cache (local memory by default),
so it needs no extra service. It resets when the server process restarts.
"""
from django.conf import settings
from django.core.cache import cache


def _key(email: str) -> str:
    return f"login-failures:{email.strip().lower()}"


def is_locked(email: str) -> bool:
    return cache.get(_key(email), 0) >= settings.LOGIN_MAX_ATTEMPTS


def register_failure(email: str) -> int:
    key = _key(email)
    failures = cache.get(key, 0) + 1
    cache.set(key, failures, settings.LOGIN_LOCKOUT_MINUTES * 60)
    return failures


def clear(email: str) -> None:
    cache.delete(_key(email))
