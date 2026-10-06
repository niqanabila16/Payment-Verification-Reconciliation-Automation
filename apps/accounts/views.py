"""Sign-in/out and the Admin user management screens (REQ: Users Management)."""
import secrets
import string

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import record
from apps.core.models import AuditLog
from apps.core.notifications import notify_role
from apps.core.permissions import role_required

from .forms import ForgotPasswordForm, LoginForm, UserForm
from .models import PasswordResetRequest, Role, User


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


def forgot_password(request):
    """
    Teller/Finance cannot change their own password, so they send a request to the Admin.
    The answer is always the same, so the page never reveals whether an email address has an account.
    """
    form = ForgotPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email__iexact=form.cleaned_data["email"], is_active=True).first()
        if user and not PasswordResetRequest.objects.filter(user=user, handled_at__isnull=True).exists():
            PasswordResetRequest.objects.create(user=user)
            record("user", user.pk, "user.password_requested", actor=user)
            notify_role(Role.ADMIN, "password_request", f"{user.name} ({user.email}) asks for a password reset.",
                        "password_request", user.pk)
        messages.success(request, "Request sent. An administrator will give you a new password.")
        return redirect("accounts:login")
    return render(request, "accounts/forgot_password.html", {"form": form})


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
    requests = PasswordResetRequest.objects.filter(handled_at__isnull=True).select_related("user")
    return render(request, "accounts/user_list.html",
                  {"page": page, "q": q, "role": role, "state": state, "roles": Role.choices, "reset_requests": requests})


@role_required(Role.ADMIN)
def user_create(request):
    form = UserForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        password = generate_temporary_password()
        user = User.objects.create_user(password=password, **{k: v for k, v in form.cleaned_data.items()})
        record("user", user.pk, "user.created", actor=request.user, role=user.role, email=user.email)
        return _credentials_page(request, user, password, "created")
    return render(request, "accounts/user_form.html", {"form": form, "mode": "create"})


@role_required(Role.ADMIN)
def user_edit(request, pk: int):
    target = get_object_or_404(User, pk=pk)
    form = UserForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        before = {"role": target.role, "branch": target.branch_id}
        if target.pk == request.user.pk and form.cleaned_data["role"] != Role.ADMIN:
            form.add_error("role", "You cannot remove your own Admin role. Ask another administrator to change it.")
        else:
            user = form.save()
            record("user", user.pk, "user.updated", actor=request.user, before=before,
                   after={"role": user.role, "branch": user.branch_id})
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
def user_reset_password(request, pk: int):
    """Admin-only password reset (users cannot change or reset their own password)."""
    target = get_object_or_404(User, pk=pk)
    password = generate_temporary_password()
    target.set_password(password)
    target.save(update_fields=["password"])
    PasswordResetRequest.objects.filter(user=target, handled_at__isnull=True).update(
        handled_at=timezone.now(), handled_by=request.user)
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
    return render(request, "accounts/audit_log.html", {"page": page, "q": q})
