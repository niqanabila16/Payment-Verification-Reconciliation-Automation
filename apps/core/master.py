"""
Admin-managed value lists behind every dropdown: branches, banks, payment methods, relationships.

Nothing is locked after it is typed: codes and names can be changed, values can be deactivated (hidden from dropdowns,
history kept) or deleted when they are no longer needed. A value that receipts or users still point to cannot be deleted
(the history would break); the message then says to deactivate it instead.
"""
import re

from django import forms
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Branch, Role, User

from .audit import record
from .forms_base import StyledFormMixin
from .models import Bank, PaymentMethod, Relationship, TransactionDescription
from .permissions import role_required

KINDS = {
    "branches": {"model": Branch, "title": "Branches", "singular": "branch", "fields": ["code", "name"]},
    "banks": {"model": Bank, "title": "Banks", "singular": "bank", "fields": ["code", "name", "statement_format"]},
    "payment-methods": {"model": PaymentMethod, "title": "Payment methods", "singular": "payment method", "fields": ["code", "name"]},
    "relationships": {"model": Relationship, "title": "Relationships", "singular": "relationship", "fields": ["code", "name"]},
    # Options of the Finance "Transaction description" filter (revision 2). The code is derived from the name, so it is not typed.
    "transaction-descriptions": {"model": TransactionDescription, "title": "Transaction descriptions", "singular": "transaction description", "fields": ["name", "bank"]},
}
CODE_PATTERN = re.compile(r"^[A-Z0-9_-]+$")


def _config(kind: str) -> dict:
    if kind not in KINDS:
        raise Http404
    return KINDS[kind]


class BaseMasterForm(StyledFormMixin, forms.ModelForm):
    """Code + name (+ statement reader for banks), shared by all four value lists."""

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if self._meta.model is TransactionDescription:
            code = TransactionDescription.make_code(name)
            if not code:
                raise forms.ValidationError("Type the description as the bank prints it.")
            if TransactionDescription.objects.filter(code=code).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError("This description already exists.")
        return name

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if not CODE_PATTERN.match(code):
            raise forms.ValidationError("Use capital letters, digits, hyphen or underscore only (no spaces).")
        return code


def _form_class(cfg):
    labels = {"code": "Code", "name": "Name", "statement_format": "Statement reader", "bank": "Only for bank (optional)"}
    return forms.modelform_factory(cfg["model"], form=BaseMasterForm, fields=cfg["fields"], labels=labels)


def usage(kind: str, obj) -> int:
    """How many records still point to this value (blocks deleting it)."""
    from apps.receipts.models import TellerSubmission
    from apps.reconciliation.models import StatementImport

    if kind == "branches":
        return User.objects.filter(branch=obj).count() + TellerSubmission.objects.filter(branch=obj).count()
    if kind == "banks":
        return TellerSubmission.objects.filter(bank=obj).count() + StatementImport.objects.filter(bank=obj).count()
    if kind == "transaction-descriptions":
        return 0   # only a filter option; no record points to it
    if kind == "payment-methods":
        return TellerSubmission.objects.filter(payment_method_code=obj.code).count()
    return TellerSubmission.objects.filter(relationship=obj.code).count()


def _rename_code_everywhere(kind: str, old: str, new: str) -> int:
    """Receipts store the code as text, so changing a code must rewrite it on those receipts too."""
    from apps.receipts.models import TellerSubmission

    if kind == "payment-methods":
        return TellerSubmission.objects.filter(payment_method_code=old).update(payment_method_code=new)
    if kind == "relationships":
        return TellerSubmission.objects.filter(relationship=old).update(relationship=new)
    return 0   # branches and banks are linked by id; nothing to rewrite


@role_required(Role.ADMIN)
def master_list(request, kind: str):
    cfg = _config(kind)
    model = cfg["model"]
    form = _form_class(cfg)(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        record(kind, obj.pk, "master.created", actor=request.user, code=obj.code, name=obj.name)
        messages.success(request, f"Added {cfg['singular']} {obj.code}.")
        return redirect("core:master_list", kind=kind)
    rows = list(model.objects.order_by("-is_active", "name" if kind == "transaction-descriptions" else "code"))
    for row in rows:
        row.in_use = usage(kind, row)
    return render(request, "core/master_list.html", {"kind": kind, "cfg": cfg, "kinds": KINDS, "form": form, "rows": rows})


@role_required(Role.ADMIN)
def master_edit(request, kind: str, pk: int):
    cfg = _config(kind)
    obj = get_object_or_404(cfg["model"], pk=pk)
    old_code = obj.code
    form = _form_class(cfg)(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        rewritten = _rename_code_everywhere(kind, old_code, saved.code) if saved.code != old_code else 0
        record(kind, saved.pk, "master.updated", actor=request.user, old_code=old_code, code=saved.code, name=saved.name, receipts_updated=rewritten)
        messages.success(request, f"Saved {cfg['singular']} {saved.code}." + (f" {rewritten} receipt(s) now use the new code." if rewritten else ""))
        return redirect("core:master_list", kind=kind)
    return render(request, "core/master_form.html", {"kind": kind, "cfg": cfg, "form": form, "obj": obj})


@role_required(Role.ADMIN)
@require_POST
def master_toggle(request, kind: str, pk: int):
    cfg = _config(kind)
    obj = get_object_or_404(cfg["model"], pk=pk)
    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])
    record(kind, obj.pk, "master.activated" if obj.is_active else "master.deactivated", actor=request.user, code=obj.code)
    messages.success(request, f"{obj.code} is now {'active' if obj.is_active else 'inactive'}.")
    return redirect("core:master_list", kind=kind)


@role_required(Role.ADMIN)
@require_POST
def master_delete(request, kind: str, pk: int):
    cfg = _config(kind)
    obj = get_object_or_404(cfg["model"], pk=pk)
    used = usage(kind, obj)
    if used:
        messages.error(request, f"{obj.code} is still used by {used} record(s) and cannot be deleted. Deactivate it instead.")
        return redirect("core:master_list", kind=kind)
    code = obj.code
    obj.delete()
    record(kind, pk, "master.deleted", actor=request.user, code=code)
    messages.success(request, f"{code} was deleted.")
    return redirect("core:master_list", kind=kind)
