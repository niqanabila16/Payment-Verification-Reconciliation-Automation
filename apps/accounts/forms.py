"""Forms for sign-in and the Admin user management screens."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm

from apps.core.forms_base import StyledFormMixin

from .models import Branch, Role, User


class LoginForm(StyledFormMixin, AuthenticationForm):
    """E-mail + password sign-in with friendly, specific error messages."""

    username = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    error_messages = {
        "invalid_login": "The email address or password is incorrect. Check both and try again.",
        "inactive": "This account has been deactivated. Ask an administrator to reactivate it.",
    }


class ForgotPasswordForm(StyledFormMixin, forms.Form):
    """Teller / Finance ask the Admin to reset their password."""

    email = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
                             error_messages={"required": "Enter the email address you sign in with."})


class UserForm(StyledFormMixin, forms.ModelForm):
    """Create / edit an operational account (name, e-mail, role, branch)."""

    class Meta:
        model = User
        fields = ["name", "email", "role", "branch"]
        labels = {"name": "Full name", "email": "Email address", "role": "Role", "branch": "Branch"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(is_active=True) | Branch.objects.filter(pk=self.instance.branch_id)
        self.fields["branch"].empty_label = "Select a branch"
        self.fields["role"].choices = [("", "Select a role")] + list(Role.choices)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email address. Use a different address.")
        return email

    def clean(self):
        cleaned = super().clean()
        role, branch = cleaned.get("role"), cleaned.get("branch")
        if role == Role.TELLER and not branch:
            self.add_error("branch", "Choose a branch. Tellers must belong to one so their receipts are tagged automatically.")
        if role in (Role.FINANCE, Role.ADMIN) and branch:
            cleaned["branch"] = None  # Finance/Admin are not tied to a branch
        return cleaned
