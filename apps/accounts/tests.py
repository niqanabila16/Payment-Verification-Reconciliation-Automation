"""Authentication, role access, user management and password rules."""
from django.core.cache import cache
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import Role, User
from apps.core.models import AuditLog
from apps.core.testing import PASSWORD, make_world


class AccessControlTests(TestCase):
    def setUp(self):
        self.w = make_world()
        cache.clear()

    def login(self, who):
        self.assertTrue(self.client.login(username=f"{who}@t.test", password=PASSWORD))

    def test_anonymous_users_are_sent_to_sign_in(self):
        for name in ("reconciliation:queue", "receipts:new", "accounts:user_list", "core:notifications"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("accounts:login"), response["Location"])

    def test_role_matrix(self):
        expected = {  # (role, url name) -> status
            ("teller", "receipts:new"): 200, ("teller", "reconciliation:queue"): 403, ("teller", "accounts:user_list"): 403,
            ("teller", "reconciliation:import_list"): 403,
            ("finance", "reconciliation:queue"): 200, ("finance", "receipts:new"): 403, ("finance", "accounts:user_list"): 403,
            ("finance", "reconciliation:import_list"): 200,
            ("admin", "accounts:user_list"): 200, ("admin", "reconciliation:queue"): 200, ("admin", "receipts:new"): 403,
            ("admin", "reconciliation:import_list"): 403,
        }
        for (role, name), status in expected.items():
            self.client.logout()
            self.login(role)
            self.assertEqual(self.client.get(reverse(name)).status_code, status, f"{role} -> {name}")

    def test_admin_cannot_decide_on_matches(self):
        self.login("admin")
        self.assertEqual(self.client.post(reverse("reconciliation:close", args=[1]), {"reason": "x" * 20}).status_code, 403)

    def test_landing_page_depends_on_role(self):
        for role, name in (("teller", "receipts:new"), ("finance", "reconciliation:queue"), ("admin", "accounts:user_list")):
            self.client.logout()
            self.login(role)
            self.assertRedirects(self.client.get("/"), reverse(name), fetch_redirect_response=False)

    def test_security_headers_present(self):
        self.login("finance")
        response = self.client.get(reverse("reconciliation:queue"))
        self.assertIn("default-src 'self'", response["Content-Security-Policy"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn("<script>", response.content.decode().replace("<script src=", ""))   # no inline scripts

    def test_login_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(reverse("accounts:login"), {"username": "finance@t.test", "password": "wrong"})
        response = self.client.post(reverse("accounts:login"), {"username": "finance@t.test", "password": PASSWORD})
        self.assertEqual(response.status_code, 429)

    def test_deactivated_user_cannot_sign_in(self):
        User.objects.filter(email="teller@t.test").update(is_active=False)
        response = self.client.post(reverse("accounts:login"), {"username": "teller@t.test", "password": PASSWORD})
        self.assertContains(response, "deactivated")
        wrong = self.client.post(reverse("accounts:login"), {"username": "teller@t.test", "password": "nope"})
        self.assertNotContains(wrong, "deactivated")                                       # wrong password reveals nothing

    def test_deactivation_ends_an_existing_session(self):
        self.login("teller")
        self.assertEqual(self.client.get(reverse("receipts:new")).status_code, 200)
        User.objects.filter(email="teller@t.test").update(is_active=False)
        self.assertEqual(self.client.get(reverse("receipts:new")).status_code, 302)   # sent back to sign-in

    def test_wrong_password_message_does_not_reveal_which_part_is_wrong(self):
        response = self.client.post(reverse("accounts:login"), {"username": "nobody@t.test", "password": "x"})
        self.assertContains(response, "email address or password is incorrect")


class PasswordPolicyTests(TestCase):
    """BR: Teller and Finance cannot change or reset their own password; only an Admin can."""

    def setUp(self):
        self.w = make_world()

    def test_no_self_service_password_routes_exist(self):
        for name in ("password_change", "password_reset", "accounts:password_change"):
            with self.assertRaises(NoReverseMatch):
                reverse(name)
        for path in ("/accounts/password_change/", "/accounts/password_reset/", "/accounts/reset/"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_admin_reset_changes_the_password_and_shows_it_once(self):
        self.client.login(username="admin@t.test", password=PASSWORD)
        response = self.client.post(reverse("accounts:user_reset_password", args=[self.w["teller"].pk]))
        self.assertEqual(response.status_code, 200)
        new_password = response.context["password"]
        self.assertEqual(response["Cache-Control"], "no-store")
        self.client.logout()
        self.assertFalse(self.client.login(username="teller@t.test", password=PASSWORD))
        self.assertTrue(self.client.login(username="teller@t.test", password=new_password))
        self.assertTrue(AuditLog.objects.filter(action="user.password_reset").exists())


class UserManagementTests(TestCase):
    def setUp(self):
        self.w = make_world()
        self.client.login(username="admin@t.test", password=PASSWORD)

    def test_create_user_with_temporary_password(self):
        response = self.client.post(reverse("accounts:user_create"), {
            "name": "New Teller", "email": "New@T.test", "role": Role.TELLER, "branch": self.w["pj"].pk})
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(email="new@t.test")                       # e-mail normalised to lower case
        self.assertTrue(user.check_password(response.context["password"]))

    def test_teller_requires_a_branch(self):
        response = self.client.post(reverse("accounts:user_create"), {"name": "X", "email": "x@t.test", "role": Role.TELLER})
        self.assertContains(response, "Choose a branch")

    def test_duplicate_email_rejected(self):
        response = self.client.post(reverse("accounts:user_create"), {"name": "X", "email": "TELLER@t.test", "role": Role.FINANCE})
        self.assertContains(response, "already uses this email")

    def test_change_role_teller_to_finance_clears_branch(self):
        response = self.client.post(reverse("accounts:user_edit", args=[self.w["teller"].pk]), {
            "name": "Teller KJ", "email": "teller@t.test", "role": Role.FINANCE, "branch": self.w["kj"].pk})
        self.assertRedirects(response, reverse("accounts:user_list"))
        user = User.objects.get(email="teller@t.test")
        self.assertEqual((user.role, user.branch), (Role.FINANCE, None))

    def test_admin_cannot_demote_or_deactivate_self(self):
        admin = self.w["admin"]
        response = self.client.post(reverse("accounts:user_edit", args=[admin.pk]), {
            "name": "Admin", "email": "admin@t.test", "role": Role.FINANCE})
        self.assertContains(response, "cannot remove your own Admin role")
        self.client.post(reverse("accounts:user_toggle_active", args=[admin.pk]))
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)

    def test_deactivate_and_reactivate_keeps_history(self):
        target = self.w["teller"]
        self.client.post(reverse("accounts:user_toggle_active", args=[target.pk]))
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.client.post(reverse("accounts:user_toggle_active", args=[target.pk]))
        target.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertEqual(AuditLog.objects.filter(entity_type="user", entity_id=target.pk).count(), 2)
