"""Audit trail integrity, notifications API, and a smoke test that renders every page for every role."""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.audit import record
from apps.core.models import AuditLog, Notification
from apps.reconciliation.models import ReconciliationMatch
from apps.reconciliation.services.engine import run_matching
from apps.core.testing import PASSWORD, credit_row, make_world, receipt, upload_statement


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

    def test_opening_the_list_marks_everything_read_without_a_button(self):
        mine = Notification.objects.create(recipient=self.w["teller"], type="t", message="hello")
        other = Notification.objects.create(recipient=self.w["teller2"], type="t", message="not mine")
        response = self.client.get(reverse("core:notifications"))
        self.assertContains(response, "hello")                          # shown as new in this response...
        self.assertContains(response, "notif--unread")
        self.assertNotContains(response, "Mark all as read")
        self.assertNotContains(response, "Showing")
        mine.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(mine.status, "read")                           # ...and read afterwards
        self.assertEqual(other.status, "unread")                        # someone else's stays untouched
        self.assertNotContains(self.client.get(reverse("core:notifications")), "notif--unread")

    def test_whole_list_is_shown_without_paging(self):
        for i in range(45):
            Notification.objects.create(recipient=self.w["teller"], type="t", message=f"message {i}")
        html = self.client.get(reverse("core:notifications")).content.decode()
        self.assertEqual(html.count('class="notif'), 45)
        self.assertNotIn("Next", html)

    def test_clicking_a_notification_goes_to_the_item(self):
        sub = receipt(self.w["teller"], self.w["rhb"], "10.00", "NOTIFYREF123")
        Notification.objects.create(recipient=self.w["teller"], type="result_gfp", message="ok",
                                    related_entity_type="submission", related_entity_id=sub.pk)
        self.assertContains(self.client.get(reverse("core:notifications")), reverse("receipts:detail", args=[sub.pk]))

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
        self.w = make_world()
        self.sub = receipt(self.w["teller"], self.w["rhb"], "150.00", "REF123456")
        self.imp = upload_statement(self.w["finance"], [credit_row("REF123456", "150.00"), credit_row("REF9999999", "40.00")])
        self.match = self.sub.match

    def get(self, role, name, *args, **params):
        self.client.logout()
        self.client.login(username=f"{role}@t.test", password=PASSWORD)
        return self.client.get(reverse(name, args=args), params)

    def test_teller_pages(self):
        for name, args in (("receipts:new", ()), ("receipts:list", ()), ("receipts:detail", (self.sub.pk,)), ("core:notifications", ())):
            self.assertEqual(self.get("teller", name, *args).status_code, 200, name)

    def test_finance_pages(self):
        for name, args in (("reconciliation:queue", ()), ("reconciliation:detail", (self.match.pk,)),
                           ("reconciliation:import_list", ()), ("reconciliation:import_detail", (self.imp.pk,))):
            self.assertEqual(self.get("finance", name, *args).status_code, 200, name)
        for tab in ("pending", "review", "rejected", "not_found", "open_item", "verified", "all"):
            self.assertEqual(self.get("finance", "reconciliation:queue", tab=tab).status_code, 200, tab)

    def test_finance_filters_and_report(self):
        self.client.login(username="finance@t.test", password=PASSWORD)
        rhb = self.w["rhb"].pk
        self.assertEqual(self.client.get(reverse("reconciliation:queue"), {"tab": "all", "bank": rhb, "q": "REF1234"}).status_code, 200)
        live = self.client.get(reverse("reconciliation:queue"), {"tab": "all", "q": "REF"}, HTTP_X_LIVE_SEARCH="1")
        self.assertEqual(live.status_code, 200)
        self.assertNotIn("<html", live.content.decode())                    # fragment only
        report = self.client.get(reverse("reconciliation:report"), {"period": "monthly", "date": "2026-10-09"})
        self.assertEqual(report.status_code, 200)
        self.assertIn("spreadsheetml", report["Content-Type"])
        self.client.logout()
        self.client.login(username="teller@t.test", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("reconciliation:report"), {"period": "monthly", "date": "2026-10-09"}).status_code, 403)

    def test_admin_pages(self):
        for name, args in (("accounts:user_list", ()), ("accounts:user_create", ()), ("accounts:audit_log", ()),
                           ("accounts:user_edit", (self.w["teller"].pk,)), ("core:master_list", ("branches",)),
                           ("core:master_list", ("banks",)), ("core:master_list", ("payment-methods",)),
                           ("core:master_list", ("relationships",)), ("core:master_list", ("transaction-descriptions",))):
            self.assertEqual(self.get("admin", name, *args).status_code, 200, name)

    def test_detail_shows_green_for_identical_and_red_for_different(self):
        review_sub = receipt(self.w["teller"], self.w["rhb"], "50.00", "REF9999999")        # the bank row says 40.00
        run_matching()
        match = ReconciliationMatch.objects.get(teller_submission=review_sub)
        html = self.get("finance", "reconciliation:detail", match.pk).content.decode()
        self.assertIn("is-diff", html)
        self.assertNotIn("Candidate", html)                                               # no list of unrelated "potential matches"
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


class MasterDataTests(TestCase):
    """Admin manages the values behind every dropdown (branch, bank, payment method, relationship)."""

    def setUp(self):
        self.w = make_world()
        self.client.login(username="admin@t.test", password=PASSWORD)

    def add(self, kind, code, name):
        return self.client.post(reverse("core:master_list", args=[kind]), {"code": code, "name": name})

    def test_admin_can_add_to_every_list(self):
        from apps.accounts.models import Branch
        from apps.core.models import Bank, PaymentMethod, Relationship
        for kind, model in (("branches", Branch), ("banks", Bank), ("payment-methods", PaymentMethod), ("relationships", Relationship)):
            response = self.add(kind, "new-code", "New value")
            self.assertRedirects(response, reverse("core:master_list", args=[kind]))
            self.assertEqual(model.objects.get(code="NEW-CODE").name, "New value")     # code is upper-cased

    def test_validation_and_unique_codes(self):
        self.assertContains(self.add("banks", "bad code", "X"), "no spaces")
        self.add("banks", "CIMB", "CIMB Bank")
        self.assertContains(self.add("banks", "cimb", "Again"), "already exists")
        self.assertContains(self.add("banks", "TOOLONGCODE" * 5, "X"), "at most")

    def test_nothing_is_locked_code_and_name_can_change(self):
        from apps.core.models import PaymentMethod
        method = PaymentMethod.objects.get(code="CASH")
        self.client.post(reverse("core:master_edit", args=["payment-methods", method.pk]), {"code": "cash2", "name": "Cash on counter"})
        method.refresh_from_db()
        self.assertEqual((method.code, method.name), ("CASH2", "Cash on counter"))

    def test_changing_a_code_updates_existing_receipts(self):
        from apps.core.models import PaymentMethod
        sub = receipt(self.w["teller"], self.w["rhb"], "10.00", "RENAMEREF123")
        method = PaymentMethod.objects.get(code="TRANSFER")
        self.client.post(reverse("core:master_edit", args=["payment-methods", method.pk]), {"code": "BANKTRF", "name": method.name})
        sub.refresh_from_db()
        self.assertEqual(sub.payment_method_code, "BANKTRF")

    def test_bank_reader_can_be_chosen(self):
        from apps.core.models import Bank
        response = self.client.post(reverse("core:master_list", args=["banks"]), {"code": "cimb", "name": "CIMB", "statement_format": "alb"})
        self.assertRedirects(response, reverse("core:master_list", args=["banks"]))
        self.assertEqual(Bank.objects.get(code="CIMB").statement_format, "alb")

    def test_delete_unused_value_is_allowed_and_used_value_is_blocked(self):
        from apps.core.models import Bank, Relationship
        self.add("banks", "cimb", "CIMB")
        cimb = Bank.objects.get(code="CIMB")
        self.client.post(reverse("core:master_delete", args=["banks", cimb.pk]))
        self.assertFalse(Bank.objects.filter(code="CIMB").exists())
        receipt(self.w["teller"], self.w["rhb"], "10.00", "DELETEREF123")
        rhb = self.w["rhb"]
        self.client.post(reverse("core:master_delete", args=["banks", rhb.pk]))
        self.assertTrue(Bank.objects.filter(pk=rhb.pk).exists())
        # a relationship nobody used yet can be deleted
        rel = Relationship.objects.exclude(code="SELF").first()
        self.client.post(reverse("core:master_delete", args=["relationships", rel.pk]))

    def test_the_four_bank_categories_exist(self):
        from apps.core.models import Bank
        self.assertEqual(set(Bank.objects.filter(is_active=True).values_list("code", flat=True)), {"RHB", "ALB", "PBB", "MBB"})

    def test_deactivate_hides_value_but_history_stays(self):
        from apps.core.models import Relationship
        rel = Relationship.objects.get(code="FRIEND")
        sub = receipt(self.w["teller"], self.w["rhb"], "10.00", "HISTORY12345")
        self.client.post(reverse("core:master_toggle", args=["relationships", rel.pk]))
        rel.refresh_from_db()
        self.assertFalse(rel.is_active)
        from apps.receipts.forms import ReceiptForm
        self.assertNotIn("FRIEND", [c[0] for c in ReceiptForm().fields["relationship"].choices])
        sub.refresh_from_db()
        self.assertEqual(sub.relationship_label, "Self (sender owns the account)")

    def test_unknown_list_is_404(self):
        self.assertEqual(self.client.get("/manage/master-data/unknown/").status_code, 404)

    def test_inactive_branch_is_not_offered_in_user_form(self):
        self.w["pj"].is_active = False
        self.w["pj"].save()
        from apps.accounts.forms import UserForm
        self.assertNotIn(self.w["pj"], list(UserForm().fields["branch"].queryset))
