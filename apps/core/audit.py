"""One-line helper to write to the append-only audit trail."""
from .models import AuditLog


def record(entity_type: str, entity_id: int, action: str, actor=None, **payload) -> AuditLog:
    """Store an audit entry. `payload` is saved as JSON, so pass plain values only."""
    safe = {key: (str(value) if not isinstance(value, (int, float, bool, type(None), dict, list)) else value)
            for key, value in payload.items()}
    return AuditLog.objects.create(entity_type=entity_type, entity_id=entity_id, action=action,
                                   actor=actor if getattr(actor, "pk", None) else None, payload=safe)
