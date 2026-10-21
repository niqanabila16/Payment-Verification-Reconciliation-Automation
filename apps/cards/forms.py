from django import forms
from django.conf import settings

from apps.accounts.models import Branch
from apps.core.forms_base import StyledFormMixin

from .models import CARD_NO_MAX, CardReason, FollowUp, RejectReason, RequestStatus


class CardFileForm(forms.Form):
    file = forms.FileField(label="Card file (.xlsx or .csv)", widget=forms.ClearableFileInput(attrs={"class": "input", "accept": ".xlsx,.csv"}))


class DeliverForm(forms.Form):
    branch = forms.ModelChoiceField(Branch.objects.none(), label="Destination branch", empty_label="Choose a branch", widget=forms.Select(attrs={"class": "input"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(is_active=True).order_by("code")


class BlockForm(forms.Form):
    note = forms.CharField(label="Reason for blocking", min_length=3, max_length=255, widget=forms.TextInput(attrs={"class": "input", "placeholder": "Reason (note)"}))


class StatusForm(forms.Form):
    """CS: the new status; for a Reject also the type (Incomplete Data / Return / Close) and the reason, both from a list."""

    status = forms.TypedChoiceField(coerce=int, choices=[(RequestStatus.ACTIVATION_REQUESTED, "Activation Requested"), (RequestStatus.ACTIVATED, "Card Activated"),
                                                         (RequestStatus.REJECTED, "Reject")])
    follow_up = forms.TypedChoiceField(coerce=int, required=False, empty_value=None, choices=FollowUp.choices)
    reject_reason = forms.TypedChoiceField(coerce=int, required=False, empty_value=None, choices=RejectReason.choices)


class CardRequestForm(StyledFormMixin, forms.Form):
    """Teller: the customer data + the customer's PDF + the card. The card number is the fixed BIN + what the Teller types."""

    customer_name = forms.CharField(label="Name", max_length=100, widget=forms.TextInput(attrs={"autocomplete": "off", "data-input-rule": "letters"}))
    account_no = forms.CharField(label="Account No", max_length=20, widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "data-input-rule": "digits"}))
    id_no = forms.CharField(label="ID No", max_length=20, widget=forms.TextInput(attrs={"autocomplete": "off", "data-input-rule": "alnum"}))
    phone = forms.CharField(label="Phone No", max_length=20, widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "off", "data-input-rule": "phone"}))
    reason = forms.TypedChoiceField(label="Reason for card", coerce=int, choices=[("", "Choose a reason")] + CardReason.choices)
    card_suffix = forms.CharField(label="Card No", max_length=CARD_NO_MAX - 6,
                                  widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "list": "card-options", "data-input-rule": "digits", "data-card-suggest": ""}))
    file = forms.FileField(label="Customer PDF file", widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"}))

    @property
    def bin(self) -> str:
        return settings.CARD_BIN

    def full_card_no(self) -> str:
        return self.bin + (self.cleaned_data.get("card_suffix") or "")
