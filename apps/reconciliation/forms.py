"""Forms for the Finance screens."""
from django import forms
from django.conf import settings

from apps.accounts.models import Branch
from apps.core.forms_base import StyledFormMixin
from apps.core.models import Bank


class StatementUploadForm(StyledFormMixin, forms.Form):
    bank = forms.ModelChoiceField(
        label="Bank", queryset=Bank.objects.all(), empty_label="Select the bank of this statement",
        error_messages={"required": "Select the bank this statement was downloaded from."})
    file = forms.FileField(
        label="Bank statement file",
        help_text=f"CSV or XLSX downloaded from the bank website, up to {settings.MAX_UPLOAD_MB} MB. "
                  f"Row {settings.STATEMENT_HEADER_ROW} must be the column header row.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
        error_messages={"required": "Choose a statement file to upload."})
    account_number = forms.CharField(
        label="Account number", required=False, max_length=30,
        help_text="Only needed if the upload fails because row 1 cannot be read.")
    statement_date = forms.DateField(
        label="Statement date", required=False, widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Only needed if the upload fails because row 1 cannot be read.")

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(settings.ALLOWED_STATEMENT_EXTENSIONS):
            raise forms.ValidationError("This file type is not supported. Save the statement as .csv or .xlsx and upload it again.")
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f"The file is larger than {settings.MAX_UPLOAD_MB} MB. Download a shorter period.")
        return upload


class CommentForm(StyledFormMixin, forms.Form):
    comment = forms.CharField(
        label="Add a comment", max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Write a message to the other party..."}),
        error_messages={"required": "Write a message before sending."})


class NoteForm(StyledFormMixin, forms.Form):
    note = forms.CharField(label="Note", required=False, max_length=500,
                           widget=forms.Textarea(attrs={"rows": 2}))


class ReassignForm(StyledFormMixin, forms.Form):
    branch = forms.ModelChoiceField(label="Move to branch", queryset=Branch.objects.all(), empty_label="Select a branch")
