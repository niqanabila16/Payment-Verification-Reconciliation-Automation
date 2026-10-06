"""
Display names for the codes stored on receipts (payment method, relationship).

Receipts store only the short code (DBML columns are plain varchar). Admin can rename the display
name at any time, so labels are looked up here. Results are cached and the cache is cleared whenever
a master-data row is saved or deleted (see signals.py).
"""
from django.core.cache import cache

from .models import PaymentMethod, Relationship

MODELS = {"payment_method": PaymentMethod, "relationship": Relationship}


def label_map(kind: str) -> dict[str, str]:
    key = f"labels:{kind}"
    data = cache.get(key)
    if data is None:
        data = dict(MODELS[kind].objects.values_list("code", "name"))
        cache.set(key, data, 300)
    return data


def label(kind: str, code: str) -> str:
    """Name for a stored code; falls back to the code itself if the value list no longer has it."""
    return label_map(kind).get(code, code or "-")


def clear_labels(**_kwargs) -> None:
    for kind in MODELS:
        cache.delete(f"labels:{kind}")
