"""
Admin-managed value lists behind every dropdown: branches, banks, payment methods, relationships.

Rules: values are added and renamed here; they are deactivated instead of deleted so old receipts
keep their history. The code cannot be changed after creation because receipts store it.
"""
import re

from django import forms
from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Branch, Role, User

from .audit import record
from .forms_base import StyledFormMixin
from .models import Bank, PaymentMethod, Relationship
from .permissions import role_required

KINDS = {
    "branches": {"model": Branch, "title": "Branches", "singular": "branch"},
    "banks": {"model": Bank, "title": "Banks", "singular": "bank"},
    "payment-methods": {"model": PaymentMethod, "title": "Payment methods", "singular": "payment method"},
    "relationships": {"model": Relationship, "title": "Relationships", "singular": "relationship"},
}
CODE_PATTERN = re.compile(r"^[A-Z0-9_-]+$")


def _config(kind: str) -> dict:
    if kind not in KINDS:
        raise Http404
    return KINDS[kind]


class BaseMasterForm(StyledFormMixin, forms.ModelForm):
    """Code + name form shared by all four value lists (the model is attached by _form_class)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:                      # receipts store the code, so it is fixed after creation
            self.fields["code"].disabled = True

    def clean_code(self):
        if self.instance.pk:
            return self.instance.code
        code = self.cleaned_data["code"].strip().upper()
        if not CODE_PATTERN.match(code):
            raise forms.ValidationError("Use capital letters, digits, hyphen or underscore only (no spaces).")
        return code


def _form_class(model):
    return forms.modelform_factory(model, form=BaseMasterForm, fields=["code", "name"],
                                   labels={"code": "Code", "name": "Name"})


@role_required(Role.ADMIN)
def master_list(request, kind: str):
    cfg = _config(kind)
    model = cfg["model"]
    form = _form_class(model)(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        record(kind, obj.pk, "master.created", actor=request.user, code=obj.code, name=obj.name)
        messages.success(request, f"Added {cfg['singular']} {obj.code}.")
        return redirect("core:master_list", kind=kind)
    return render(request, "core/master_list.html", {
        "kind": kind, "cfg": cfg, "kinds": KINDS, "form": form, "rows": model.objects.order_by("-is_active", "code"),
    })


@role_required(Role.ADMIN)
def master_edit(request, kind: str, pk: int):
    cfg = _config(kind)
    obj = get_object_or_404(cfg["model"], pk=pk)
    form = _form_class(cfg["model"])(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        record(kind, obj.pk, "master.updated", actor=request.user, code=obj.code, name=obj.name)
        messages.success(request, f"Saved {cfg['singular']} {obj.code}.")
        return redirect("core:master_list", kind=kind)
    return render(request, "core/master_form.html", {"kind": kind, "cfg": cfg, "form": form, "obj": obj})


@role_required(Role.ADMIN)
@require_POST
def master_toggle(request, kind: str, pk: int):
    cfg = _config(kind)
    obj = get_object_or_404(cfg["model"], pk=pk)
    if obj.is_active:  # guard rails when deactivating
        if kind == "banks" and obj.code == settings.STATEMENT_BANK_CODE:
            messages.error(request, f"{obj.name} receives every uploaded statement and cannot be deactivated.")
            return redirect("core:master_list", kind=kind)
        if kind == "branches":
            users = User.objects.filter(branch=obj, is_active=True).count()
            if users:
                messages.error(request, f"{users} active user(s) belong to branch {obj.code}. Move or deactivate them first.")
                return redirect("core:master_list", kind=kind)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    record(kind, obj.pk, "master.activated" if obj.is_active else "master.deactivated", actor=request.user, code=obj.code)
    messages.success(request, f"{obj.code} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("core:master_list", kind=kind)
