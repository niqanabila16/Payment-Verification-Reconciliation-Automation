"""
Receipt form for Tellers.

NFR-PERF-2: length rules are enforced twice, in the browser (HTML minlength/maxlength/pattern)
and here on the server, so a request that bypasses the browser is still rejected.
"""
import re
import uuid

from django import forms
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.core.forms_base import StyledFormMixin
from apps.core.models import Bank, PaymentMethod, Relationship
from apps.core.normalize import normalize_reference

from .models import TellerSubmission

ALLOWED_REFERENCE_CHARS = re.compile(r"^[A-Za-z0-9 \-./]+$")


class ReceiptForm(StyledFormMixin, forms.Form):
    client_uuid = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    entered_at = forms.DateTimeField(widget=forms.HiddenInput, required=False)

    sender_name = forms.CharField(label="Sender name", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "off"}))
    account_holder_name = forms.CharField(label="Account holder name", max_length=150,
                                          widget=forms.TextInput(attrs={"autocomplete": "off"}))
    relationship = forms.ChoiceField(
        label="Relationship to sender", choices=[],
        error_messages={"required": "Select the sender's relationship to the account holder."},
    )
    bank = forms.ModelChoiceField(
        label="Bank", queryset=Bank.objects.none(), empty_label="Select a bank",
        error_messages={"required": "Select the bank that received the payment."},
    )
    payment_method_code = forms.ChoiceField(
        label="Payment method", choices=[],
        error_messages={"required": "Select how the customer paid."},
    )
    amount = forms.DecimalField(
        label="Amount (RM)", min_value=0.01, max_value=9999999.99, decimal_places=2, max_digits=12,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
        error_messages={"invalid": "Enter the amount as a number, for example 150.00."},
    )
    bank_reference_no = forms.CharField(
        label="Bank reference number",
        help_text=f"{settings.REFERENCE_MIN_LENGTH} to {settings.REFERENCE_MAX_LENGTH} letters or digits",
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dropdown values are managed by the Admin (Master data). Inactive values stay visible only when
        # the receipt being edited already uses them.
        current = (self.initial or {})
        self.fields["bank"].queryset = Bank.objects.filter(Q(is_active=True) | Q(pk=current.get("bank")))
        self.fields["relationship"].choices = [("", "Select a relationship")] + [
            (r.code, r.name) for r in Relationship.objects.filter(Q(is_active=True) | Q(code=current.get("relationship")))]
        self.fields["payment_method_code"].choices = [("", "Select a payment method")] + [
            (m.code, m.name) for m in PaymentMethod.objects.filter(Q(is_active=True) | Q(code=current.get("payment_method_code")))]
        low, high = settings.REFERENCE_MIN_LENGTH, settings.REFERENCE_MAX_LENGTH
        ref_widget = self.fields["bank_reference_no"].widget
        ref_widget.attrs.update({
            "minlength": low, "maxlength": high + 6,   # allows a few separator characters
            "pattern": r"[A-Za-z0-9 \-./]+",
            "title": f"{low} to {high} letters or digits. Spaces and hyphens are allowed.",
        })

    def clean_bank_reference_no(self):
        raw = self.cleaned_data["bank_reference_no"].strip()
        low, high = settings.REFERENCE_MIN_LENGTH, settings.REFERENCE_MAX_LENGTH
        if not ALLOWED_REFERENCE_CHARS.match(raw):
            raise forms.ValidationError("Use only letters, digits, spaces, hyphens, dots or slashes.")
        size = len(normalize_reference(raw))
        if size < low or size > high:
            raise forms.ValidationError(
                f"The reference must contain {low} to {high} letters or digits (you entered {size}). "
                "Check the proof of payment and type the full reference."
            )
        return raw

    def clean(self):
        cleaned = super().clean()
        ref, amount, bank, client_uuid = (cleaned.get(k) for k in
                                          ("bank_reference_no", "amount", "bank", "client_uuid"))
        if ref and amount is not None and bank:
            duplicate = (TellerSubmission.objects
                         .filter(reference_normalized=normalize_reference(ref), amount=amount, bank=bank)
                         .exclude(client_uuid=client_uuid).first())
            if duplicate:
                status = duplicate.match.get_match_status_display() if hasattr(duplicate, "match") else "Pending"
                self.add_error("bank_reference_no", (
                    f"This data was already saved on {timezone.localtime(duplicate.entered_at):%d %b %Y at %H:%M} "
                    f"with verification status \"{status}\" (receipt #{duplicate.pk}). Do not enter it again."
                ))
        return cleaned
