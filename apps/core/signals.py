"""Clear the label cache when master data changes."""
from django.db.models.signals import post_delete, post_save

from .lookups import clear_labels
from .models import PaymentMethod, Relationship


def connect() -> None:
    for model in (PaymentMethod, Relationship):
        post_save.connect(clear_labels, sender=model, dispatch_uid=f"labels-save-{model.__name__}")
        post_delete.connect(clear_labels, sender=model, dispatch_uid=f"labels-delete-{model.__name__}")
