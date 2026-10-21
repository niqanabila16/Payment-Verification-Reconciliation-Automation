"""Forms for the Finance screens."""
from django import forms
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import Branch
from apps.core.forms_base import StyledFormMixin
from apps.core.models import Bank, TransactionDescription


class StatementUploadForm(StyledFormMixin, forms.Form):
    bank = forms.ModelChoiceField(
        label="Bank", queryset=Bank.objects.none(), empty_label="Select bank",
        error_messages={"required": "Select the bank this statement comes from."})
    file = forms.FileField(
        label="Bank statement (CSV or XLSX)",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
        error_messages={"required": "Choose a statement file to upload."})
    # Shown only after row 1 of an RHB file could not be read.
    account_number = forms.CharField(label="Account number", required=False, max_length=30)
    statement_date = forms.DateField(label="Statement date", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active banks that have a statement reader can be chosen.
        self.fields["bank"].queryset = Bank.objects.filter(is_active=True).exclude(statement_format="")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(settings.ALLOWED_STATEMENT_EXTENSIONS):
            raise forms.ValidationError("This file type is not supported. Save the statement as .csv or .xlsx and upload it again.")
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"The file is larger than {settings.MAX_UPLOAD_MB} MB. Download a shorter period.")
        return upload


class ReportForm(StyledFormMixin, forms.Form):
    period = forms.ChoiceField(label="Report", choices=[("weekly", "Weekly (Monday to Sunday)"), ("monthly", "Monthly")], initial="weekly")
    date = forms.DateField(label="Any date in the period", widget=forms.DateInput(attrs={"type": "date"}), initial=timezone.localdate)
    bank = forms.ModelChoiceField(label="Bank", queryset=Bank.objects.none(), required=False, empty_label="All banks")
    description = forms.ChoiceField(label="Transaction description", required=False, choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bank"].queryset = Bank.objects.exclude(statement_format="")
        names = TransactionDescription.objects.filter(is_active=True).order_by("name").values_list("name", flat=True).distinct()
        self.fields["description"].choices = [("", "All descriptions")] + [(n, n) for n in names]
        self.fields["date"].initial = timezone.localdate()
