"""
Receipt form for Tellers.

NFR-PERF-2: length rules are enforced twice, in the browser (HTML minlength/maxlength/pattern)
and here on the server, so a request that bypasses the browser is still rejected.
"""
import re
import uuid
from datetime import timedelta

from django import forms
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.core.forms_base import StyledFormMixin
from apps.core.models import Bank, PaymentMethod, Relationship
from apps.core.normalize import normalize_reference, parse_teller_amount

from .models import TellerSubmission, submission_fingerprint

REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9]+$")                   # letters and digits only: nothing else can be typed or sent
NAME_PATTERN = re.compile(r"^[^\W\d_]+(?: [^\W\d_]+)*$")              # letters only, words separated by single spaces

NAME_ATTRS = {"data-input-rule": "letters", "pattern": r"[A-Za-z\u00C0-\u024F ]+", "title": "Letters and spaces only (no digits or symbols)."}


class ReceiptForm(StyledFormMixin, forms.Form):
    client_uuid = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    entered_at = forms.DateTimeField(widget=forms.HiddenInput, required=False)

    # Same fields as before this revision; the only new input is the transaction date and time.
    sender_name = forms.CharField(label="Sender name", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "off", **NAME_ATTRS}))
    account_holder_name = forms.CharField(label="Account holder name", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "off", **NAME_ATTRS}))
    relationship = forms.ChoiceField(label="Relationship to sender", choices=[],
                                     error_messages={"required": "Select the sender's relationship to the account holder."})
    payment_method_code = forms.ChoiceField(label="Payment method", choices=[],
                                            error_messages={"required": "Select how the customer paid."})
    bank = forms.ModelChoiceField(label="Bank", queryset=Bank.objects.none(), empty_label="Select a bank",
                                  error_messages={"required": "Select the bank that received the payment."})
    amount = forms.CharField(
        label="Amount (RM)", max_length=14,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off", "placeholder": "150,00",
                                      "pattern": r"\s*(RM)?\s*[0-9]+([.,][0-9]{1,2})?\s*",
                                      "title": "Ringgit, with sen after a comma, e.g. 150,50"}),
        help_text="e.g. 150,50")
    transaction_at = forms.DateTimeField(
        label="Transaction date and time",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"],
        help_text="As printed on the receipt",
        error_messages={"required": "Enter the date and time printed on the receipt.", "invalid": "Enter a valid date and time."})
    bank_reference_no = forms.CharField(
        label="Bank reference number",
        help_text=f"{settings.REFERENCE_MIN_LENGTH} to {settings.REFERENCE_MAX_LENGTH} letters or digits, no spaces or symbols",
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false", "data-input-rule": "alnum"}),
    )

    def __init__(self, *args, submission=None, **kwargs):
        self.submission = submission          # set when a Teller corrects an existing receipt (edit screen)
        super().__init__(*args, **kwargs)
        # Dropdown values are managed by the Admin (Master data). Inactive values stay visible only when
        # the receipt being edited already uses them.
        current = self.initial or {}
        self.fields["bank"].queryset = Bank.objects.filter(Q(is_active=True) | Q(pk=current.get("bank")))
        self.fields["relationship"].choices = [("", "Select a relationship")] + [
            (r.code, r.name) for r in Relationship.objects.filter(Q(is_active=True) | Q(code=current.get("relationship")))]
        self.fields["payment_method_code"].choices = [("", "Select a payment method")] + [
            (m.code, m.name) for m in PaymentMethod.objects.filter(Q(is_active=True) | Q(code=current.get("payment_method_code")))]
        low, high = settings.REFERENCE_MIN_LENGTH, settings.REFERENCE_MAX_LENGTH
        self.fields["bank_reference_no"].widget.attrs.update({
            "minlength": low, "maxlength": high,
            "pattern": r"[A-Za-z0-9]+",
            "title": f"{low} to {high} letters or digits only.",
        })
        # The browser must not offer a time in the future.
        self.fields["transaction_at"].widget.attrs["max"] = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        self._apply_aria()

    def _clean_name(self, field):
        value = " ".join((self.cleaned_data.get(field) or "").split())
        if not NAME_PATTERN.match(value):
            raise forms.ValidationError("Use letters only (no digits, dots, slashes or other symbols).")
        return value

    def clean_sender_name(self):
        return self._clean_name("sender_name")

    def clean_account_holder_name(self):
        return self._clean_name("account_holder_name")

    def clean_amount(self):
        try:
            return parse_teller_amount(self.cleaned_data["amount"])
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_transaction_at(self):
        when = self.cleaned_data["transaction_at"]
        if when > timezone.now() + timedelta(minutes=5):
            raise forms.ValidationError("The transaction time cannot be in the future. Check the time printed on the receipt.")
        return when

    def clean_bank_reference_no(self):
        raw = self.cleaned_data["bank_reference_no"].strip()
        low, high = settings.REFERENCE_MIN_LENGTH, settings.REFERENCE_MAX_LENGTH
        if not REFERENCE_PATTERN.match(raw):
            raise forms.ValidationError("Use only letters and digits (no spaces or symbols).")
        size = len(normalize_reference(raw))
        if size < low or size > high:
            raise forms.ValidationError(
                f"The reference must contain {low} to {high} letters or digits (you entered {size}). "
                "Check the proof of payment and type the full reference."
            )
        return raw

    def clean(self):
        cleaned = super().clean()
        ref, amount, client_uuid = cleaned.get("bank_reference_no"), cleaned.get("amount"), cleaned.get("client_uuid")
        self.duplicate = None
        self.repeat = None
        if ref and amount is not None and cleaned.get("account_holder_name"):
            # The same person (name: at least two words in common, any order), the same amount AND the same reference number was
            # entered before, in ANY status (verified, pending, reject) by ANY branch. A different reference number means a
            # different transaction, so a customer who pays the same amount again later never triggers the warning.
            holder = cleaned["account_holder_name"]
            candidates = (TellerSubmission.objects.select_related("branch", "match")
                          .filter(reference_normalized=normalize_reference(ref), amount=amount)
                          .exclude(client_uuid=client_uuid).order_by("-entered_at"))
            self.duplicate = next((c for c in candidates if same_person(holder, c.account_holder_name)), None)
            if self.duplicate:
                self.add_error("bank_reference_no", duplicate_message(self.duplicate))
        if self.submission is not None and not self.duplicate and not self.errors:
            # A correction must change something: the same values as now, or as any earlier version, were already entered.
            bank = cleaned.get("bank")
            fingerprint = submission_fingerprint(cleaned.get("sender_name"), cleaned.get("account_holder_name"), cleaned.get("relationship"),
                                                 bank.pk if bank else None, cleaned.get("amount"), cleaned.get("bank_reference_no"),
                                                 cleaned.get("payment_method_code"), cleaned.get("transaction_at"))
            if fingerprint == self.submission.fingerprint or fingerprint in (self.submission.previous_versions or []):
                self.repeat = self.submission
                self.add_error(None, "These values were already entered for this receipt. Correct what Finance asked for before saving.")
        return cleaned

    @property
    def popup(self):
        """What the red pop-up shows (or None): another receipt with the same name, amount and reference, or an unchanged correction."""
        if getattr(self, "duplicate", None):
            return duplicate_info(self.duplicate)
        if getattr(self, "repeat", None):
            return duplicate_info(self.repeat, kind="unchanged")
        return None

    @property
    def duplicate_only(self):
        """True when the duplicate warning is the only error, so there is nothing for the teller to fix."""
        return bool(getattr(self, "duplicate", None)) and set(self.errors) == {"bank_reference_no"}


def same_person(name_a: str, name_b: str) -> bool:
    """Names are the same person when at least NAME_MATCH_MIN_WORDS words are shared, whatever the order (one-word names must be equal)."""
    from apps.reconciliation.services.engine import shared_name_words

    shared, needed = shared_name_words(name_a, name_b)
    return needed > 0 and shared >= needed


TELLER_STATUS_LABELS = {"gfp": "Verified", "rejected": "Reject", "pending": "Pending"}
POPUP_TEXT = {
    "duplicate": ("Already entered", "This transaction was entered before. It cannot be entered again."),
    "unchanged": ("Nothing was corrected", "These values were already entered for this receipt. Fix what Finance asked for (see the note) and save again."),
}


def duplicate_info(sub, kind: str = "duplicate") -> dict:
    """What the red pop-up shows: who already entered it, with name, amount and identifier."""
    title, message = POPUP_TEXT[kind]
    return {"kind": kind, "title": title, "message": message,
        "branch": sub.branch.code, "branch_name": sub.branch.name,
        "account_holder": sub.account_holder_name, "sender": sub.sender_name,
        "amount": f"RM {sub.amount:,.2f}", "reference": sub.bank_reference_no,
        "entered": timezone.localtime(sub.entered_at).strftime("%d %b %Y %H:%M"),
        "status": TELLER_STATUS_LABELS[sub.match.teller_status],
    }


def duplicate_message(sub) -> str:
    info = duplicate_info(sub)
    return (f"Already entered by branch {info['branch']} on {info['entered']}: {info['account_holder']}"
            f"{' / ' + info['sender'] if info['sender'] else ''}, {info['amount']}, reference {info['reference']} "
            f"(status {info['status']}). Do not enter it again.")
