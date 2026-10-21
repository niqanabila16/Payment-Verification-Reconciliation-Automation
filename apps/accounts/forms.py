"""Forms for sign-in and the Admin user management screens."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.core.cache import cache

from apps.core.forms_base import StyledFormMixin

from .models import Branch, CsPerm, Role, User


class LoginForm(StyledFormMixin, AuthenticationForm):
    """E-mail + password sign-in with friendly, specific error messages."""

    username = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    error_messages = {
        "invalid_login": "The email address or password is incorrect. Check both and try again.",
        "inactive": "This account has been deactivated. Ask an administrator to reactivate it.",
    }


class ForgotPasswordForm(StyledFormMixin, PasswordResetForm):
    """
    "Forgot password": the user enters the e-mail address and receives a unique, time-limited link.
    The answer is the same whether or not the address has an account. Sending again within one minute is ignored,
    so the form cannot be used to flood someone's mailbox.
    """

    email = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}),
                             error_messages={"required": "Enter the email address you sign in with."})

    def get_users(self, email):
        if not cache.add(f"password-reset-sent:{email.strip().lower()}", 1, 60):
            return []
        return super().get_users(email)


class NewPasswordForm(StyledFormMixin, SetPasswordForm):
    """Set a new password and confirm it. The rules come from AUTH_PASSWORD_VALIDATORS (10+ characters, not common)."""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].label = "New password"
        self.fields["new_password2"].label = "Confirm new password"
        self.fields["new_password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["new_password2"].widget.attrs["autocomplete"] = "new-password"
        self.error_messages = {**self.error_messages, "password_mismatch": "The two passwords are different. Type the same password twice."}
        self._bound_fields_cache = {}   # the mixin already built bound fields with the old label / hint text
        self._apply_aria()


class UserForm(StyledFormMixin, forms.ModelForm):
    """Create / edit an operational account (name, e-mail, role, branch)."""

    cs_rights = forms.MultipleChoiceField(
        label="Customer service rights", required=False, choices=CsPerm.CHOICES, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = User
        fields = ["name", "email", "role", "branch"]
        labels = {"name": "Full name", "email": "Email address", "role": "Role", "branch": "Branch"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = self.instance.cs_permissions if self.instance.pk else CsPerm.DEFAULT
        self.fields["cs_rights"].initial = [str(v) for v, _ in CsPerm.CHOICES if current & v]
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
        if role in (Role.FINANCE, Role.ADMIN, Role.CS) and branch:
            cleaned["branch"] = None  # Finance, Admin and Customer service are not tied to a branch
        bits = sum(int(v) for v in cleaned.get("cs_rights") or [])
        cleaned["cs_permissions"] = bits if role == Role.CS else 0
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.cs_permissions = self.cleaned_data.get("cs_permissions", user.cs_permissions)
        if commit:
            user.save()
        return user
