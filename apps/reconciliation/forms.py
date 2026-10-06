"""Forms for the Finance screens."""
from django import forms
from django.conf import settings

from apps.accounts.models import Branch
from apps.core.forms_base import StyledFormMixin


class StatementUploadForm(StyledFormMixin, forms.Form):
    file = forms.FileField(
        label="Bank statement (CSV or XLSX)",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
        error_messages={"required": "Choose a statement file to upload."})
    # Shown only after row 1 of a file could not be read.
    account_number = forms.CharField(label="Account number", required=False, max_length=30)
    statement_date = forms.DateField(label="Statement date", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(settings.ALLOWED_STATEMENT_EXTENSIONS):
            raise forms.ValidationError("This file type is not supported. Save the statement as .csv or .xlsx and upload it again.")
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"The file is larger than {settings.MAX_UPLOAD_MB} MB. Download a shorter period.")
        return upload


class ReassignForm(StyledFormMixin, forms.Form):
    branch = forms.ModelChoiceField(label="Move to branch", queryset=Branch.objects.none(), empty_label="Select a branch")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(is_active=True)
