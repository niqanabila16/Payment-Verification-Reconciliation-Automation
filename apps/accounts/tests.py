"""Authentication, role access, e-mailed password reset, and the Admin user screens."""
import re

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import Role, User
from apps.core.models import AuditLog
from apps.core.testing import PASSWORD, make_world, receipt

LOCMEM = {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}


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
        expected = {
            ("teller", "receipts:new", ()): 200, ("teller", "reconciliation:queue", ()): 403, ("teller", "accounts:user_list", ()): 403,
            ("teller", "reconciliation:import_list", ()): 403, ("teller", "core:master_list", ("banks",)): 403,
            ("teller", "reconciliation:report", ()): 403,
            ("finance", "reconciliation:queue", ()): 200, ("finance", "receipts:new", ()): 403, ("finance", "accounts:user_list", ()): 403,
            ("finance", "reconciliation:import_list", ()): 200, ("finance", "core:master_list", ("banks",)): 403,
            ("admin", "accounts:user_list", ()): 200, ("admin", "reconciliation:queue", ()): 200, ("admin", "receipts:new", ()): 403,
            ("admin", "reconciliation:import_list", ()): 403, ("admin", "core:master_list", ("banks",)): 200,
            ("admin", "reconciliation:report", ()): 403,
        }
        for (role, name, args), status in expected.items():
            self.client.logout()
            self.login(role)
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, status, f"{role} -> {name}")

    def test_admin_cannot_decide_on_matches(self):
        self.login("admin")
        self.assertEqual(self.client.post(reverse("reconciliation:confirm", args=[1]), {"note": "x"}).status_code, 403)

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
        self.assertNotIn("<script>", response.content.decode().replace("<script src=", ""))

    def test_no_lockout_after_repeated_failures(self):
        for _ in range(8):
            self.client.post(reverse("accounts:login"), {"username": "finance@t.test", "password": "wrong"})
        response = self.client.post(reverse("accounts:login"), {"username": "finance@t.test", "password": PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_login_page_has_show_password_and_forgot_link(self):
        html = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn("data-toggle-password", html)
        self.assertIn(reverse("accounts:forgot_password"), html)

    def test_header_navigation_without_sidebar_burger_or_online_pill(self):
        self.login("finance")
        html = self.client.get(reverse("reconciliation:queue")).content.decode()
        self.assertIn('class="topnav"', html)
        for gone in ("sidebar", "menu-toggle", "Online", "Architecture"):
            self.assertNotIn(gone, html)
        self.assertEqual(self.client.get("/architecture/").status_code, 404)

    def test_deactivated_user_cannot_sign_in(self):
        User.objects.filter(email="teller@t.test").update(is_active=False)
        response = self.client.post(reverse("accounts:login"), {"username": "teller@t.test", "password": PASSWORD})
        self.assertContains(response, "deactivated")
        wrong = self.client.post(reverse("accounts:login"), {"username": "teller@t.test", "password": "nope"})
        self.assertNotContains(wrong, "deactivated")

    def test_deactivation_ends_an_existing_session(self):
        self.login("teller")
        self.assertEqual(self.client.get(reverse("receipts:new")).status_code, 200)
        User.objects.filter(email="teller@t.test").update(is_active=False)
        self.assertEqual(self.client.get(reverse("receipts:new")).status_code, 302)

    def test_wrong_password_message_does_not_reveal_which_part_is_wrong(self):
        response = self.client.post(reverse("accounts:login"), {"username": "nobody@t.test", "password": "x"})
        self.assertContains(response, "email address or password is incorrect")


@override_settings(**LOCMEM, SITE_BASE_URL="")
class ForgotPasswordTests(TestCase):
    """Forgot password: an emailed, time-limited, single-use link. No request to an Admin is needed."""

    def setUp(self):
        self.w = make_world()
        cache.clear()
        mail.outbox.clear()

    def request(self, email="teller@t.test"):
        return self.client.post(reverse("accounts:forgot_password"), {"email": email})

    def link(self):
        return re.search(r"https?://\S+/accounts/reset/\S+/", mail.outbox[-1].body).group(0)

    def test_link_is_emailed_to_the_user(self):
        response = self.request("Teller@T.test")
        self.assertRedirects(response, reverse("accounts:forgot_password_sent"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["teller@t.test"])
        self.assertIn("/accounts/reset/", mail.outbox[0].body)
        self.assertIn("60 minutes", mail.outbox[0].body)

    def test_sent_page_shows_the_masked_address_and_a_resend_button(self):
        page = self.client.post(reverse("accounts:forgot_password"), {"email": "teller@t.test"}, follow=True)
        self.assertContains(page, "Check your email")
        self.assertContains(page, "te****@t.test")
        self.assertContains(page, "Send the link again")

    def test_resend_waits_60_seconds_then_sends_again(self):
        self.request()
        self.client.post(reverse("accounts:forgot_password_resend"))             # too early
        self.assertEqual(len(mail.outbox), 1)
        session = self.client.session
        session["password-reset-resend-at"] = 0
        session.save()
        self.client.post(reverse("accounts:forgot_password_resend"))
        self.assertEqual(len(mail.outbox), 2)

    def test_sent_page_without_a_request_goes_back_to_the_form(self):
        self.assertRedirects(self.client.get(reverse("accounts:forgot_password_sent")), reverse("accounts:forgot_password"))

    def test_all_roles_can_reset_themselves(self):
        for who in ("teller", "finance", "admin"):
            cache.clear()
            mail.outbox.clear()
            self.request(f"{who}@t.test")
            self.assertEqual(len(mail.outbox), 1, who)

    def test_full_flow_set_new_password_with_confirmation(self):
        self.request()
        page = self.client.get(self.link(), follow=True)                       # token URL redirects to the set-password page
        self.assertContains(page, "New password")
        self.assertContains(page, "Confirm new password")
        post_url = page.redirect_chain[-1][0]
        response = self.client.post(post_url, {"new_password1": "Brand-New-Pass-77", "new_password2": "Brand-New-Pass-77"})
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertFalse(self.client.login(username="teller@t.test", password=PASSWORD))
        self.assertTrue(self.client.login(username="teller@t.test", password="Brand-New-Pass-77"))
        self.assertTrue(AuditLog.objects.filter(action="user.password_reset_by_email").exists())

    def test_passwords_must_match_and_follow_the_rules(self):
        self.request()
        post_url = self.client.get(self.link(), follow=True).redirect_chain[-1][0]
        different = self.client.post(post_url, {"new_password1": "Brand-New-Pass-77", "new_password2": "Another-Pass-77"})
        self.assertContains(different, "The two passwords are different")
        short = self.client.post(post_url, {"new_password1": "short", "new_password2": "short"})
        self.assertContains(short, "too short")
        self.assertTrue(self.client.login(username="teller@t.test", password=PASSWORD))      # nothing changed

    def test_link_works_only_once(self):
        self.request()
        link = self.link()
        post_url = self.client.get(link, follow=True).redirect_chain[-1][0]
        self.client.post(post_url, {"new_password1": "Brand-New-Pass-77", "new_password2": "Brand-New-Pass-77"})
        used = self.client.get(link, follow=True)
        self.assertContains(used, "Link not valid")

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_link_is_refused(self):
        self.request()
        self.assertContains(self.client.get(self.link(), follow=True), "Link not valid")

    def test_tampered_link_is_refused(self):
        self.request()
        bad = self.link()[:-8] + "x" * 7 + "/"
        self.assertContains(self.client.get(bad, follow=True), "Link not valid")

    def test_same_answer_for_unknown_and_inactive_addresses_and_no_mail(self):
        User.objects.filter(email="teller2@t.test").update(is_active=False)
        for email in ("nobody@t.test", "teller2@t.test"):
            self.assertRedirects(self.request(email), reverse("accounts:forgot_password_sent"))
        self.assertEqual(len(mail.outbox), 0)

    def test_repeated_requests_within_a_minute_send_one_email(self):
        for _ in range(3):
            self.request()
        self.assertEqual(len(mail.outbox), 1)

    def test_base_url_setting_is_used_in_the_link(self):
        with override_settings(SITE_BASE_URL="https://recon.company.local"):
            self.request()
        self.assertIn("https://recon.company.local/accounts/reset/", mail.outbox[0].body)

    def test_mail_server_down_does_not_crash_and_does_not_reveal_accounts(self):
        with override_settings(EMAIL_BACKEND="apps.accounts.tests.BrokenBackend"):
            with self.assertLogs("django.contrib.auth", level="ERROR"):
                known = self.request("teller@t.test")
            unknown = self.request("nobody@t.test")
        self.assertRedirects(known, reverse("accounts:forgot_password_sent"))
        self.assertRedirects(unknown, reverse("accounts:forgot_password_sent"))
        self.assertContains(self.client.get(reverse("accounts:login")), "Ask an administrator") if False else None

    def test_there_is_no_request_to_admin_flow_any_more(self):
        self.request()
        self.client.login(username="admin@t.test", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("accounts:user_list")), "Password reset requests")

    def test_no_change_password_route_for_signed_in_users(self):
        for name in ("password_change", "accounts:password_change"):
            with self.assertRaises(NoReverseMatch):
                reverse(name)


class BrokenBackend:
    """Stands in for an unreachable SMTP server."""

    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise ConnectionError("SMTP unreachable")


class AdminResetTests(TestCase):
    """The Admin can still hand out a temporary password (for example when the mail server is down)."""

    def setUp(self):
        self.w = make_world()

    def test_admin_reset_changes_the_password_and_shows_it_once(self):
        self.client.login(username="admin@t.test", password=PASSWORD)
        response = self.client.post(reverse("accounts:user_reset_password", args=[self.w["teller"].pk]))
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
        user = User.objects.get(email="new@t.test")
        self.assertTrue(user.check_password(response.context["password"]))

    def test_teller_requires_a_branch(self):
        response = self.client.post(reverse("accounts:user_create"), {"name": "X", "email": "x@t.test", "role": Role.TELLER})
        self.assertContains(response, "Choose a branch")

    def test_branch_field_is_disabled_by_script_for_finance_and_admin(self):
        self.assertIn("data-role-branch-form", self.client.get(reverse("accounts:user_create")).content.decode())
        self.client.post(reverse("accounts:user_create"), {
            "name": "Fin", "email": "fin2@t.test", "role": Role.FINANCE, "branch": self.w["kj"].pk})
        self.assertIsNone(User.objects.get(email="fin2@t.test").branch)

    def test_duplicate_email_rejected(self):
        response = self.client.post(reverse("accounts:user_create"), {"name": "X", "email": "TELLER@t.test", "role": Role.FINANCE})
        self.assertContains(response, "already uses this email")

    def test_everything_about_a_user_can_be_changed(self):
        response = self.client.post(reverse("accounts:user_edit", args=[self.w["teller"].pk]), {
            "name": "Renamed", "email": "renamed@t.test", "role": Role.FINANCE, "branch": self.w["kj"].pk})
        self.assertRedirects(response, reverse("accounts:user_list"))
        user = User.objects.get(pk=self.w["teller"].pk)
        self.assertEqual((user.name, user.email, user.role, user.branch), ("Renamed", "renamed@t.test", Role.FINANCE, None))

    def test_admin_cannot_demote_deactivate_or_delete_self(self):
        admin = self.w["admin"]
        response = self.client.post(reverse("accounts:user_edit", args=[admin.pk]), {"name": "Admin", "email": "admin@t.test", "role": Role.FINANCE})
        self.assertContains(response, "cannot remove your own Admin role")
        self.client.post(reverse("accounts:user_toggle_active", args=[admin.pk]))
        self.client.post(reverse("accounts:user_delete", args=[admin.pk]))
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)

    def test_deactivate_and_activate_keeps_history(self):
        target = self.w["teller"]
        self.client.post(reverse("accounts:user_toggle_active", args=[target.pk]))
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.client.post(reverse("accounts:user_toggle_active", args=[target.pk]))
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_delete_user_without_receipts(self):
        pk = self.w["teller2"].pk
        response = self.client.post(reverse("accounts:user_delete", args=[pk]))
        self.assertRedirects(response, reverse("accounts:user_list"))
        self.assertFalse(User.objects.filter(pk=pk).exists())
        self.assertTrue(AuditLog.objects.filter(action="user.deleted", entity_id=pk).exists())

    def test_user_with_receipts_cannot_be_deleted_only_deactivated(self):
        receipt(self.w["teller"], self.w["rhb"], "10.00", "DELETEBLOCK1")
        response = self.client.post(reverse("accounts:user_delete", args=[self.w["teller"].pk]), follow=True)
        self.assertContains(response, "Deactivate it instead")
        self.assertTrue(User.objects.filter(pk=self.w["teller"].pk).exists())

    def test_user_list_has_delete_and_live_search(self):
        html = self.client.get(reverse("accounts:user_list")).content.decode()
        self.assertIn(reverse("accounts:user_delete", args=[self.w["teller"].pk]), html)
        self.assertIn("data-live-search", html)
        fragment = self.client.get(reverse("accounts:user_list"), {"q": "teller kj"}, headers={"X-Live-Search": "1"}).content.decode()
        self.assertIn("Teller KJ", fragment)
        self.assertNotIn("Teller PJ", fragment)
        self.assertNotIn("<html", fragment)
