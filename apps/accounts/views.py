"""Sign-in/out and the Admin user management screens (REQ: Users Management)."""
import secrets
import string

from django.conf import settings
import time

from django.contrib import messages
from django.core.cache import cache
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetView
from django.core.paginator import Paginator
from django.urls import reverse_lazy
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.audit import record
from apps.core.models import AuditLog
from apps.core.permissions import role_required

from .forms import ForgotPasswordForm, LoginForm, NewPasswordForm, UserForm
from .models import Role, User


class SignInView(LoginView):
    """Sign-in with audit logging."""

    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_valid(self, form):
        record("user", form.get_user().pk, "user.login", actor=form.get_user())
        return super().form_valid(form)

    def form_invalid(self, form):
        record("user", 0, "user.login_failed", email=self.request.POST.get("username", ""))
        return super().form_invalid(form)


class ForgotPasswordView(PasswordResetView):
    """Sends the reset link by e-mail (see templates/accounts/password_reset_email.txt)."""

    form_class = ForgotPasswordForm
    template_name = "accounts/forgot_password.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:forgot_password_sent")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["minutes"] = settings.PASSWORD_RESET_TIMEOUT // 60
        return context

    def form_valid(self, form):
        self.extra_email_context = {"base_url": settings.SITE_BASE_URL, "minutes": settings.PASSWORD_RESET_TIMEOUT // 60}
        response = super().form_valid(form)   # Django logs (and hides) an SMTP failure so the page cannot reveal which addresses exist
        record("user", 0, "user.password_reset_requested", email=form.cleaned_data["email"])
        self.request.session[RESET_EMAIL_KEY] = form.cleaned_data["email"].strip().lower()
        self.request.session["password-reset-resend-at"] = int(time.time())
        return response


RESET_EMAIL_KEY = "password-reset-email"
RESEND_SECONDS = 60


def _mask(email: str) -> str:
    name, _, domain = email.partition("@")
    return (name[:2] + "*" * max(len(name) - 2, 1)) + "@" + domain


def forgot_password_sent(request):
    """"Check your email" page: where the link was sent, a Resend button (60 s cooldown) and the way back."""
    email = request.session.get(RESET_EMAIL_KEY)
    if not email:
        return redirect("accounts:forgot_password")
    console = settings.DEBUG and settings.EMAIL_BACKEND.endswith("console.EmailBackend")
    resend_in = max(0, RESEND_SECONDS - (int(time.time()) - request.session.get("password-reset-resend-at", 0)))
    return render(request, "accounts/forgot_password_sent.html", {
        "email": _mask(email), "minutes": settings.PASSWORD_RESET_TIMEOUT // 60, "console_mail": console, "resend_in": resend_in})


@require_POST
def forgot_password_resend(request):
    email = request.session.get(RESET_EMAIL_KEY)
    if not email:
        return redirect("accounts:forgot_password")
    now = int(time.time())
    last = request.session.get("password-reset-resend-at", 0)
    if now - last < RESEND_SECONDS:
        messages.error(request, f"Please wait {RESEND_SECONDS - (now - last)} seconds before sending the link again.")
        return redirect("accounts:forgot_password_sent")
    cache.delete(f"password-reset-sent:{email}")          # the anti-flood marker is ours to reset: the 60 s rule above replaces it
    form = ForgotPasswordForm({"email": email})
    if form.is_valid():
        form.save(request=request, email_template_name="accounts/password_reset_email.txt", subject_template_name="accounts/password_reset_subject.txt",
                  extra_email_context={"base_url": settings.SITE_BASE_URL, "minutes": settings.PASSWORD_RESET_TIMEOUT // 60})
        record("user", 0, "user.password_reset_requested", email=email, resend=True)
    request.session["password-reset-resend-at"] = now
    messages.success(request, "The link was sent again.")
    return redirect("accounts:forgot_password_sent")


class NewPasswordView(PasswordResetConfirmView):
    """The page opened from the e-mailed link: new password + confirmation."""

    form_class = NewPasswordForm
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:login")
    post_reset_login = False

    def form_valid(self, form):
        response = super().form_valid(form)
        record("user", form.user.pk, "user.password_reset_by_email", actor=form.user)
        messages.success(self.request, "Your password was changed. Sign in with the new password.")
        return response


@require_POST
def sign_out(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("accounts:login")


# --------------------------------------------------------------------------
# Admin: users
# --------------------------------------------------------------------------
def generate_temporary_password(length: int = 12) -> str:
    """Random password that satisfies the validators (letters, digits, no ambiguous characters)."""
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0OIl1")
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd


def _credentials_page(request, user, password, reason):
    """Show the temporary password exactly once (never stored in messages/cookies)."""
    response = render(request, "accounts/credentials.html", {"target": user, "password": password, "reason": reason})
    response["Cache-Control"] = "no-store"
    return response


@role_required(Role.ADMIN)
def user_list(request):
    qs = User.objects.select_related("branch")
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    state = request.GET.get("state", "")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q))
    if role in Role.values:
        qs = qs.filter(role=role)
    if state == "active":
        qs = qs.filter(is_active=True)
    elif state == "inactive":
        qs = qs.filter(is_active=False)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    context = {"page": page, "q": q, "role": role, "state": state, "roles": Role.choices}
    if request.headers.get("X-Live-Search"):   # live search: only the part that changes
        return render(request, "accounts/_user_results.html", context)
    return render(request, "accounts/user_list.html", context)


@role_required(Role.ADMIN)
def user_create(request):
    form = UserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        password = generate_temporary_password()
        user = User.objects.create_user(password=password, **{k: v for k, v in form.cleaned_data.items() if k != "cs_rights"})
        record("user", user.pk, "user.created", actor=request.user, role=user.role, email=user.email)
        return _credentials_page(request, user, password, "created")
    return render(request, "accounts/user_form.html", {"form": form, "mode": "create"})


@role_required(Role.ADMIN)
def user_edit(request, pk: int):
    target = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        before = {"role": target.role, "branch": target.branch_id, "cs_permissions": target.cs_permissions}
        if target.pk == request.user.pk and form.cleaned_data["role"] != Role.ADMIN:
            form.add_error("role", "You cannot remove your own Admin role. Ask another administrator to change it.")
        else:
            user = form.save()
            record("user", user.pk, "user.updated", actor=request.user, before=before,
                   after={"role": user.role, "branch": user.branch_id, "cs_permissions": user.cs_permissions})
            messages.success(request, f"Saved changes for {user.name}.")
            return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "mode": "edit", "target": target})


@role_required(Role.ADMIN)
@require_POST
def user_toggle_active(request, pk: int):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("accounts:user_list")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    record("user", target.pk, "user.activated" if target.is_active else "user.deactivated", actor=request.user)
    verb = "reactivated" if target.is_active else "deactivated"
    messages.success(request, f"{target.name} was {verb}.")
    return redirect("accounts:user_list")


@role_required(Role.ADMIN)
@require_POST
def user_delete(request, pk: int):
    """
    Delete a user that is no longer needed. A user who already reported receipts cannot be deleted
    (the receipts would lose who reported them); deactivate that account instead.
    """
    from apps.receipts.models import TellerSubmission

    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot delete your own account.")
        return redirect("accounts:user_list")
    used = TellerSubmission.objects.filter(submitted_by=target).count()
    if used:
        messages.error(request, f"{target.name} reported {used} receipt(s), so the account cannot be deleted. Deactivate it instead.")
        return redirect("accounts:user_list")
    name, email = target.name, target.email
    target.delete()
    record("user", pk, "user.deleted", actor=request.user, email=email)
    messages.success(request, f"{name} was deleted.")
    return redirect("accounts:user_list")


@role_required(Role.ADMIN)
@require_POST
def user_reset_password(request, pk: int):
    """Admin-only password reset (users cannot change or reset their own password)."""
    target = get_object_or_404(User, pk=pk)
    password = generate_temporary_password()
    target.set_password(password)
    target.save(update_fields=["password"])
    record("user", target.pk, "user.password_reset", actor=request.user)
    return _credentials_page(request, target, password, "reset")


@role_required(Role.ADMIN)
def audit_log(request):
    """Read-only view of the append-only audit trail (NFR-010)."""
    qs = AuditLog.objects.select_related("actor")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(action__icontains=q) | Q(entity_type__icontains=q) | Q(actor__name__icontains=q))
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    if request.headers.get("X-Live-Search"):
        return render(request, "accounts/_audit_results.html", {"page": page, "q": q})
    return render(request, "accounts/audit_log.html", {"page": page, "q": q})
