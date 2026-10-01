"""Audit trail integrity, notifications API, and a smoke test that renders every page for every role."""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.audit import record
from apps.core.models import AuditLog, Notification
from apps.core.testing import PASSWORD, csv_upload, credit_row, make_world, receipt


class AuditTrailTests(TestCase):
    def test_audit_entries_are_append_only(self):
        entry = record("user", 1, "test.action")
        entry.action = "changed"
        with self.assertRaises(PermissionError):
            entry.save()
        with self.assertRaises(PermissionError):
            entry.delete()
        with self.assertRaises(PermissionError):
            AuditLog.objects.all().delete()
        with self.assertRaises(PermissionError):
            AuditLog.objects.all().update(action="x")


class NotificationApiTests(TestCase):
    def setUp(self):
        self.w = make_world()
        self.client.login(username="teller@t.test", password=PASSWORD)

    def test_poll_returns_only_my_new_notifications(self):
        mine = Notification.objects.create(recipient=self.w["teller"], type="t", message="for me")
        Notification.objects.create(recipient=self.w["teller2"], type="t", message="not mine")
        data = self.client.get(reverse("core:notification_poll") + "?after=0").json()
        self.assertEqual(data["unread"], 1)
        self.assertEqual([i["message"] for i in data["items"]], ["for me"])
        later = self.client.get(reverse("core:notification_poll") + f"?after={mine.pk}").json()
        self.assertEqual(later["items"], [])

    def test_cannot_mark_someone_elses_notification_as_read(self):
        other = Notification.objects.create(recipient=self.w["teller2"], type="t", message="x")
        self.client.post(reverse("core:notification_read", args=[other.pk]))
        other.refresh_from_db()
        self.assertEqual(other.status, "unread")

    def test_open_redirect_is_blocked(self):
        mine = Notification.objects.create(recipient=self.w["teller"], type="t", message="x")
        response = self.client.post(reverse("core:notification_read", args=[mine.pk]), {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("core:notifications"))

    def test_email_digest_only_when_enabled(self):
        from django.core import mail
        from apps.core.notifications import send_digest_email
        self.assertFalse(send_digest_email(self.w["teller"], "s", ["line"]))
        with override_settings(NOTIFY_BY_EMAIL=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            self.assertTrue(send_digest_email(self.w["teller"], "s", ["line"]))
        self.assertEqual(len(mail.outbox), 1)


@override_settings(IMPORT_RUN_SYNC=True)
class PageSmokeTests(TestCase):
    """Every screen must render (no template errors) for the roles that can open it."""

    def setUp(self):
        from apps.reconciliation.services.importer import start_import
        self.w = make_world()
        self.sub = receipt(self.w["teller"], self.w["mandiri"], "150.00", "REF123456")
        self.imp = start_import(user=self.w["finance"], bank=self.w["mandiri"], uploaded_file=csv_upload(
            [credit_row("REF123456", "150.00", "B1"), credit_row("REF9999999", "40.00", "B2")]))
        self.match = self.sub.match

    def get(self, role, name, *args, **params):
        self.client.logout()
        self.client.login(username=f"{role}@t.test", password=PASSWORD)
        return self.client.get(reverse(name, args=args), params)

    def test_teller_pages(self):
        for name, args in (("receipts:new", ()), ("receipts:list", ()), ("receipts:detail", (self.sub.pk,)),
                           ("core:notifications", ()), ("core:architecture", ())):
            self.assertEqual(self.get("teller", name, *args).status_code, 200, name)

    def test_finance_pages(self):
        for name, args in (("reconciliation:queue", ()), ("reconciliation:detail", (self.match.pk,)),
                           ("reconciliation:import_list", ()), ("reconciliation:import_detail", (self.imp.pk,))):
            self.assertEqual(self.get("finance", name, *args).status_code, 200, name)
        for tab in ("attention", "review", "unmatched", "pending", "verified", "closed", "all"):
            self.assertEqual(self.get("finance", "reconciliation:queue", tab=tab).status_code, 200, tab)

    def test_admin_pages(self):
        for name, args in (("accounts:user_list", ()), ("accounts:user_create", ()), ("accounts:audit_log", ()),
                           ("accounts:user_edit", (self.w["teller"].pk,))):
            self.assertEqual(self.get("admin", name, *args).status_code, 200, name)

    def test_detail_shows_green_for_identical_and_red_for_different(self):
        from apps.reconciliation.models import ReconciliationMatch
        typo = receipt(self.w["teller"], self.w["mandiri"], "40.00", "REF9999990")        # one character different
        from apps.reconciliation.services.engine import run_matching
        run_matching()
        match = ReconciliationMatch.objects.get(teller_submission=typo)
        html = self.get("finance", "reconciliation:detail", match.pk).content.decode()
        self.assertIn("is-diff", html)
        self.assertIn('class="chardiff"', html)
        verified = self.get("finance", "reconciliation:detail", self.match.pk).content.decode()
        self.assertIn("is-same", verified)

    def test_service_worker_and_health(self):
        self.client.login(username="teller@t.test", password=PASSWORD)
        response = self.client.get("/sw.js")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(self.client.get("/healthz/").json(), {"status": "ok"})

    def test_progress_endpoint(self):
        data = self.get("finance", "reconciliation:import_status", self.imp.pk).json()
        self.assertEqual(data["status"], "processed")
        self.assertEqual(data["progress"], 100)
