"""Teller receipt form: validation (NFR-PERF-2), branch from session, duplicates, offline sync, correction flow."""
import uuid

from django.test import TestCase
from django.urls import reverse

from apps.core.models import AuditLog
from apps.core.testing import PASSWORD, make_world, receipt
from apps.reconciliation.models import MatchStatus

from .forms import ReceiptForm
from .models import TellerSubmission


def payload(w, **overrides):
    data = {"client_uuid": str(uuid.uuid4()), "sender_name": "MOH HAIKAL", "account_holder_name": "MOH HAIKAL",
            "relationship": "SELF", "bank": w["mandiri"].pk, "payment_method_code": "TRANSFER", "amount": "150.00",
            "bank_reference_no": "2235277A1"}
    data.update(overrides)
    return data


class ReceiptFormTests(TestCase):
    def setUp(self):
        self.w = make_world()

    def test_reference_length_is_validated_on_the_server(self):
        for bad in ("123", "1" * 40):
            form = ReceiptForm(payload(self.w, bank_reference_no=bad))
            self.assertFalse(form.is_valid())
            self.assertIn("bank_reference_no", form.errors)

    def test_browser_side_length_rules_are_rendered(self):
        """NFR-PERF-2: the same limits must also exist in the HTML so the browser blocks bad input first."""
        html = str(ReceiptForm()["bank_reference_no"])
        self.assertIn('minlength="6"', html)
        self.assertIn("maxlength=", html)
        self.assertIn("pattern=", html)

    def test_reference_rejects_odd_characters(self):
        self.assertFalse(ReceiptForm(payload(self.w, bank_reference_no="REF<script>1234")).is_valid())

    def test_dropdowns_are_mandatory(self):
        form = ReceiptForm(payload(self.w, payment_method_code="", bank=""))
        self.assertFalse(form.is_valid())
        self.assertIn("payment_method_code", form.errors)
        self.assertIn("bank", form.errors)

    def test_payment_method_must_be_one_of_the_three(self):
        self.assertFalse(ReceiptForm(payload(self.w, payment_method_code="CRYPTO")).is_valid())

    def test_amount_must_be_positive(self):
        self.assertFalse(ReceiptForm(payload(self.w, amount="0")).is_valid())
        self.assertFalse(ReceiptForm(payload(self.w, amount="-5")).is_valid())


class ReceiptViewTests(TestCase):
    def setUp(self):
        self.w = make_world()
        self.client.login(username="teller@t.test", password=PASSWORD)
        self.url = reverse("receipts:new")

    def post_json(self, data):
        return self.client.post(self.url, data, headers={"Accept": "application/json"})

    def test_branch_comes_from_the_login_session_not_the_form(self):
        response = self.post_json(payload(self.w, branch=self.w["pj"].pk))   # attempt to spoof another branch
        self.assertEqual(response.status_code, 201)
        self.assertEqual(TellerSubmission.objects.get().branch, self.w["kj"])

    def test_pending_match_row_is_created_with_the_submission(self):
        self.post_json(payload(self.w))
        self.assertEqual(TellerSubmission.objects.get().match.match_status, MatchStatus.PENDING)

    def test_offline_sync_is_idempotent(self):
        data = payload(self.w)
        first, second = self.post_json(data), self.post_json(data)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(TellerSubmission.objects.count(), 1)

    def test_server_errors_return_the_rendered_form_for_ajax(self):
        response = self.post_json(payload(self.w, bank_reference_no="12"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("error-summary", response.json()["html"])

    def test_duplicate_entry_reports_time_and_status(self):
        self.post_json(payload(self.w))
        response = self.post_json(payload(self.w, bank_reference_no="2235277a1"))   # same data, new client_uuid
        self.assertEqual(response.status_code, 400)
        html = response.json()["html"]
        self.assertIn("already saved", html)
        self.assertIn("Pending", html)
        self.assertEqual(TellerSubmission.objects.count(), 1)

    def test_old_offline_timestamp_is_trusted_but_future_is_not(self):
        from datetime import timedelta
        from django.utils import timezone
        past = (timezone.now() - timedelta(hours=10)).isoformat()
        future = (timezone.now() + timedelta(days=3)).isoformat()
        self.post_json(payload(self.w, entered_at=past))
        self.post_json(payload(self.w, entered_at=future, bank_reference_no="FUTURE123456", amount="9.00"))
        old, new = TellerSubmission.objects.order_by("id")
        self.assertLess(old.entered_at, new.entered_at)
        self.assertLess(new.entered_at, timezone.now() + timedelta(minutes=1))

    def test_teller_without_branch_sees_a_clear_error(self):
        from apps.accounts.models import User
        User.objects.filter(email="teller@t.test").update(branch=None)
        self.assertContains(self.client.get(self.url), "Your account has no branch")

    def test_teller_only_sees_own_branch_receipts(self):
        other = receipt(self.w["teller2"], self.w["mandiri"], "10.00", "OTHERBRANCH1")
        self.assertEqual(self.client.get(reverse("receipts:detail", args=[other.pk])).status_code, 404)

    def test_edit_flow_after_feedback(self):
        sub = receipt(self.w["teller"], self.w["mandiri"], "150.00", "WRONGREF123")
        sub.match.match_status = MatchStatus.NOT_FOUND
        sub.match.save()
        page = self.client.get(reverse("receipts:edit", args=[sub.pk]))
        self.assertEqual(page.status_code, 200)
        data = payload(self.w, bank_reference_no="RIGHTREF123", client_uuid=str(sub.client_uuid))
        response = self.client.post(reverse("receipts:edit", args=[sub.pk]), data)
        self.assertRedirects(response, reverse("receipts:detail", args=[sub.pk]))
        sub.refresh_from_db()
        self.assertEqual(sub.reference_normalized, "RIGHTREF123")
        self.assertTrue(AuditLog.objects.filter(action="submission.corrected").exists())

    def test_verified_receipt_cannot_be_edited(self):
        sub = receipt(self.w["teller"], self.w["mandiri"], "150.00", "VERIFIED1234")
        sub.match.match_status = MatchStatus.GFP
        sub.match.save()
        response = self.client.get(reverse("receipts:edit", args=[sub.pk]))
        self.assertRedirects(response, reverse("receipts:detail", args=[sub.pk]))
