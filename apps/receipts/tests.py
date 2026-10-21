"""Teller receipt form: validation, amount with comma, transaction time, duplicate pop-up, offline sync, correction."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLog, Bank, PaymentMethod, Relationship
from apps.core.testing import PASSWORD, make_world, receipt
from apps.reconciliation.models import MatchStatus

from .forms import ReceiptForm
from .models import TellerSubmission


def when(hours_ago=2) -> str:
    return (timezone.localtime() - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M")


def payload(w, **overrides):
    data = {"client_uuid": str(uuid.uuid4()), "account_holder_name": "MOH HAIKAL", "sender_name": "MOH HAIKAL", "relationship": "SELF",
            "bank": w["rhb"].pk, "payment_method_code": "TRANSFER", "amount": "150,50", "transaction_at": when(),
            "bank_reference_no": "2235277A1"}
    data.update(overrides)
    return data


class ReceiptFormTests(TestCase):
    def setUp(self):
        self.w = make_world()

    def errors(self, **overrides):
        form = ReceiptForm(payload(self.w, **overrides))
        form.is_valid()
        return form.errors

    def test_valid_receipt_has_the_same_fields_as_before_plus_the_transaction_time(self):
        form = ReceiptForm(payload(self.w))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["amount"], Decimal("150.50"))
        self.assertEqual(list(form.fields), ["client_uuid", "entered_at", "sender_name", "account_holder_name", "relationship",
                                              "payment_method_code", "bank", "amount", "transaction_at", "bank_reference_no"])

    def test_sender_account_holder_and_relationship_stay_required(self):
        for field in ("sender_name", "account_holder_name", "relationship"):
            self.assertIn(field, self.errors(**{field: ""}))

    def test_comma_marks_the_sen_for_ringgit(self):
        for raw, expected in (("150,50", "150.50"), ("150.50", "150.50"), ("150", "150.00"), ("12,5", "12.50")):
            form = ReceiptForm(payload(self.w, amount=raw))
            self.assertTrue(form.is_valid(), (raw, form.errors))
            self.assertEqual(form.cleaned_data["amount"], Decimal(expected))

    def test_amount_rejects_thousands_separators_zero_and_text(self):
        for raw in ("1,200.50", "1.200,50", "0", "0,00", "abc", "12,345"):
            self.assertIn("amount", self.errors(amount=raw), raw)

    def test_transaction_time_is_required_and_cannot_be_in_the_future(self):
        self.assertIn("transaction_at", self.errors(transaction_at=""))
        self.assertIn("The transaction time cannot be in the future", str(self.errors(transaction_at=when(hours_ago=-5))))
        self.assertNotIn("transaction_at", self.errors(transaction_at=when(hours_ago=30)))

    def test_reference_length_is_validated_on_the_server(self):
        for bad in ("123", "1" * 40):
            self.assertIn("bank_reference_no", self.errors(bank_reference_no=bad))

    def test_browser_side_rules_are_rendered(self):
        html = str(ReceiptForm()["bank_reference_no"])
        self.assertIn('minlength="6"', html)
        self.assertIn("pattern=", html)
        self.assertIn("pattern=", str(ReceiptForm()["amount"]))
        self.assertIn('type="datetime-local"', str(ReceiptForm()["transaction_at"]))
        self.assertIn("max=", str(ReceiptForm()["transaction_at"]))

    def test_reference_rejects_odd_characters_and_spaces(self):
        for bad in ("REF<script>1234", "2235-277A1", "2235 277A1", "2235/277A1", "2235.277A1"):
            self.assertIn("bank_reference_no", self.errors(bank_reference_no=bad), bad)

    def test_names_accept_only_letters_and_spaces(self):
        for field in ("sender_name", "account_holder_name"):
            for bad in ("KARYATI LESTARI/", "ALI 2", "ALI-BIN", "A.L. RAJAN", "ALI@"):
                self.assertIn(field, self.errors(**{field: bad}), (field, bad))
            self.assertNotIn(field, self.errors(**{field: "  Nur   Aisyah "}))

    def test_inputs_carry_the_rules_the_browser_enforces_while_typing(self):
        form = ReceiptForm()
        self.assertIn('data-input-rule="alnum"', str(form["bank_reference_no"]))
        self.assertIn('data-input-rule="letters"', str(form["account_holder_name"]))
        self.assertIn('data-input-rule="letters"', str(form["sender_name"]))

    def test_dropdowns_are_mandatory_and_limited_to_the_lists(self):
        errors = self.errors(payment_method_code="", bank="")
        self.assertIn("payment_method_code", errors)
        self.assertIn("bank", errors)
        self.assertIn("payment_method_code", self.errors(payment_method_code="CRYPTO"))


class ReceiptViewTests(TestCase):
    def setUp(self):
        self.w = make_world()
        self.client.login(username="teller@t.test", password=PASSWORD)
        self.url = reverse("receipts:new")

    def post_json(self, data):
        return self.client.post(self.url, data, headers={"Accept": "application/json"})

    def test_branch_comes_from_the_login_session_not_the_form(self):
        response = self.post_json(payload(self.w, branch=self.w["pj"].pk))
        self.assertEqual(response.status_code, 201)
        sub = TellerSubmission.objects.get()
        self.assertEqual((sub.branch, sub.amount, sub.sender_name), (self.w["kj"], Decimal("150.50"), "MOH HAIKAL"))

    def test_transaction_time_is_stored(self):
        self.post_json(payload(self.w, transaction_at="2026-10-01T09:15"))
        local = timezone.localtime(TellerSubmission.objects.get().transaction_at)
        self.assertEqual(local.strftime("%Y-%m-%d %H:%M"), "2026-10-01 09:15")

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
        self.assertIn("field__error", response.json()["html"])
        self.assertNotIn("duplicate", response.json())

    def test_duplicate_from_another_branch_returns_details_for_the_red_popup(self):
        other = receipt(self.w["teller2"], self.w["rhb"], "150.50", "2235277A1", sender="SITI", holder="MOH HAIKAL")   # branch PJ
        response = self.post_json(payload(self.w))                                                                     # branch KJ
        self.assertEqual(response.status_code, 409)
        info = response.json()["duplicate"]
        self.assertEqual((info["branch"], info["account_holder"], info["sender"], info["amount"], info["reference"]),
                         ("PJ", "MOH HAIKAL", "SITI", "RM 150.50", "2235277A1"))
        self.assertEqual(info["status"], "Pending")
        self.assertEqual(TellerSubmission.objects.count(), 1)
        self.assertEqual(other.pk, TellerSubmission.objects.get().pk)

    def test_duplicate_needs_same_name_amount_and_reference_in_any_word_order_and_any_bank(self):
        receipt(self.w["teller2"], self.w["rhb"], "150.50", "2235277A1", sender="HAIKAL MOH", holder="HAIKAL MOH")
        response = self.post_json(payload(self.w, bank=self.w["alb"].pk))      # name words in another order, other bank
        self.assertEqual(response.status_code, 409)

    def test_same_name_and_amount_with_another_reference_is_a_new_transaction(self):
        receipt(self.w["teller2"], self.w["rhb"], "150.50", "OLDREF12345", sender="MOH HAIKAL", holder="MOH HAIKAL")
        self.assertEqual(self.post_json(payload(self.w)).status_code, 201)

    def test_same_reference_and_amount_with_a_different_person_is_not_a_duplicate(self):
        receipt(self.w["teller2"], self.w["rhb"], "150.50", "2235277A1", sender="SITI AMINAH", holder="SITI AMINAH")
        self.assertEqual(self.post_json(payload(self.w)).status_code, 201)

    def test_only_one_shared_name_word_is_not_enough(self):
        receipt(self.w["teller2"], self.w["rhb"], "150.50", "2235277A1", sender="MOH ZAKI", holder="MOH ZAKI")
        self.assertEqual(self.post_json(payload(self.w)).status_code, 201)

    def test_duplicate_is_found_for_verified_and_rejected_receipts_too(self):
        from apps.reconciliation.services import review
        sub = receipt(self.w["teller2"], self.w["rhb"], "150.50", "2235277A1", sender="MOH HAIKAL", holder="MOH HAIKAL")
        review.reject_receipt(sub.match, self.w["finance"], "Amaun Salah")
        response = self.post_json(payload(self.w))
        self.assertEqual((response.status_code, response.json()["duplicate"]["status"]), (409, "Reject"))
        sub.match.refresh_from_db()
        sub.match.match_status = MatchStatus.GFP
        sub.match.save()
        self.assertEqual(self.post_json(payload(self.w)).json()["duplicate"]["status"], "Verified")

    def test_duplicate_without_javascript_shows_the_branch_in_the_form_error(self):
        receipt(self.w["teller2"], self.w["rhb"], "150.50", "2235277A1", sender="MOH HAIKAL", holder="MOH HAIKAL")
        response = self.client.post(self.url, payload(self.w))
        self.assertContains(response, "Already entered by branch PJ")

    def test_same_reference_with_another_amount_is_not_a_duplicate(self):
        receipt(self.w["teller2"], self.w["rhb"], "99.00", "2235277A1", sender="MOH HAIKAL", holder="MOH HAIKAL")
        self.assertEqual(self.post_json(payload(self.w)).status_code, 201)

    def test_receipt_matches_a_waiting_open_item_at_once(self):
        from apps.core.testing import credit_row, upload_statement
        from django.test import override_settings
        with override_settings(IMPORT_RUN_SYNC=True):
            upload_statement(self.w["finance"], [credit_row("2235277A1", "150.50", name="MOH HAIKAL")])
        self.post_json(payload(self.w))
        self.assertEqual(TellerSubmission.objects.get().match.match_status, MatchStatus.GFP)

    def test_old_offline_timestamp_is_trusted_but_future_is_not(self):
        past = (timezone.now() - timedelta(hours=10)).isoformat()
        future = (timezone.now() + timedelta(days=3)).isoformat()
        self.post_json(payload(self.w, entered_at=past))
        self.post_json(payload(self.w, entered_at=future, bank_reference_no="FUTURE123456", amount="9,00"))
        old, new = TellerSubmission.objects.order_by("id")
        self.assertLess(old.entered_at, new.entered_at)
        self.assertLess(new.entered_at, timezone.now() + timedelta(minutes=1))

    def test_teller_without_branch_sees_a_clear_error(self):
        from apps.accounts.models import User
        User.objects.filter(email="teller@t.test").update(branch=None)
        self.assertContains(self.client.get(self.url), "Your account has no branch")

    def test_form_page_has_the_duplicate_dialog_and_the_new_fields(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('id="duplicate-dialog"', html)
        self.assertIn("dialog--danger", html)
        self.assertLess(html.index("Sender name"), html.index("Account holder name"))
        self.assertIn("Transaction date and time", html)

    def test_teller_only_sees_own_branch_receipts(self):
        other = receipt(self.w["teller2"], self.w["rhb"], "10.00", "OTHERBRANCH1")
        self.assertEqual(self.client.get(reverse("receipts:detail", args=[other.pk])).status_code, 404)

    def test_edit_flow_after_feedback(self):
        sub = receipt(self.w["teller"], self.w["rhb"], "150.00", "WRONGREF123")
        sub.match.match_status = MatchStatus.NOT_FOUND
        sub.match.save()
        self.assertEqual(self.client.get(reverse("receipts:edit", args=[sub.pk])).status_code, 200)
        data = payload(self.w, bank_reference_no="RIGHTREF123", client_uuid=str(sub.client_uuid), amount="150,00")
        response = self.client.post(reverse("receipts:edit", args=[sub.pk]), data)
        self.assertRedirects(response, reverse("receipts:detail", args=[sub.pk]))
        sub.refresh_from_db()
        self.assertEqual(sub.reference_normalized, "RIGHTREF123")
        self.assertTrue(AuditLog.objects.filter(action="submission.corrected").exists())

    def test_verified_receipt_cannot_be_edited(self):
        sub = receipt(self.w["teller"], self.w["rhb"], "150.00", "VERIFIED1234")
        sub.match.match_status = MatchStatus.GFP
        sub.match.save()
        self.assertRedirects(self.client.get(reverse("receipts:edit", args=[sub.pk])), reverse("receipts:detail", args=[sub.pk]))


class TellerStatusTests(TestCase):
    """Tellers see only Pending or Verified, never Not found / Review, and no discussion thread."""

    def setUp(self):
        self.w = make_world()
        self.client.login(username="teller@t.test", password=PASSWORD)

    def make(self, status, ref):
        sub = receipt(self.w["teller"], self.w["rhb"], "150.00", ref)
        sub.match.match_status = status
        sub.match.save()
        return sub

    def test_every_unresolved_state_is_shown_as_pending(self):
        for status, ref in ((MatchStatus.NOT_FOUND, "REF000000A"), (MatchStatus.MANUAL_REVIEW, "REF000000C")):
            sub = self.make(status, ref)
            html = self.client.get(reverse("receipts:detail", args=[sub.pk])).content.decode()
            self.assertIn("Pending", html)
            for hidden in ("Not found", "typo", "Review", "Discussion", "amount differs", "Open Item"):
                self.assertNotIn(hidden, html, f"{status}: {hidden}")
        self.assertNotIn("Not found", self.client.get(reverse("receipts:list")).content.decode())

    def test_rejected_receipt_shows_reject_with_the_finance_note_and_a_correct_button(self):
        from apps.reconciliation.services import review
        sub = self.make(MatchStatus.NOT_FOUND, "REF000000R")
        review.reject_receipt(sub.match, self.w["finance"], "Amaun Salah")
        html = self.client.get(reverse("receipts:detail", args=[sub.pk])).content.decode()
        self.assertIn("Reject", html)
        self.assertIn("Amaun Salah", html)
        self.assertIn(reverse("receipts:edit", args=[sub.pk]), self.client.get(reverse("receipts:list")).content.decode())

    def test_correcting_without_changes_shows_the_duplicate_popup(self):
        from apps.reconciliation.services import review
        sub = self.make(MatchStatus.NOT_FOUND, "REF000000S")
        review.reject_receipt(sub.match, self.w["finance"], "Amaun Salah")
        data = {"account_holder_name": sub.account_holder_name, "sender_name": sub.sender_name, "relationship": sub.relationship, "bank": sub.bank.pk,
                "payment_method_code": sub.payment_method_code, "amount": "150,00", "transaction_at": sub.transaction_at.astimezone().strftime("%Y-%m-%dT%H:%M"),
                "bank_reference_no": sub.bank_reference_no}
        response = self.client.post(reverse("receipts:edit", args=[sub.pk]), data)
        self.assertContains(response, "data-popup")
        sub.match.refresh_from_db()
        self.assertEqual(sub.match.match_status, MatchStatus.REJECTED)

    def test_verified_receipt_shows_verified_and_has_no_edit_button(self):
        sub = self.make(MatchStatus.GFP, "REF000000D")
        html = self.client.get(reverse("receipts:detail", args=[sub.pk])).content.decode()
        self.assertIn("Verified", html)
        self.assertNotIn("Correct receipt", html)

    def test_list_filter_and_live_search(self):
        a = self.make(MatchStatus.NOT_FOUND, "REF000000E")
        b = self.make(MatchStatus.GFP, "REF000000F")
        html = self.client.get(reverse("receipts:list"), {"status": "pending"}).content.decode()
        self.assertIn(a.bank_reference_no, html)
        self.assertNotIn(b.bank_reference_no, html)
        fragment = self.client.get(reverse("receipts:list"), {"q": "REF000000F"}, headers={"X-Live-Search": "1"}).content.decode()
        self.assertIn("REF000000F", fragment)
        self.assertNotIn("REF000000E", fragment)
        self.assertNotIn("<html", fragment)


class DropdownTests(TestCase):
    """Dropdown values come from the Admin-managed value lists."""

    def setUp(self):
        self.w = make_world()

    def test_new_and_inactive_values(self):
        PaymentMethod.objects.create(code="QR", name="DuitNow QR")
        Relationship.objects.create(code="NEIGHBOUR", name="Neighbour")
        Bank.objects.create(code="CIMB", name="CIMB Bank")
        PaymentMethod.objects.filter(code="CDM").update(is_active=False)
        Bank.objects.filter(code="ALB").update(is_active=False)
        form = ReceiptForm()
        methods = [c[0] for c in form.fields["payment_method_code"].choices]
        self.assertIn("QR", methods)
        self.assertNotIn("CDM", methods)
        self.assertIn("NEIGHBOUR", [c[0] for c in form.fields["relationship"].choices])
        banks = [b.code for b in form.fields["bank"].queryset]
        self.assertIn("CIMB", banks)
        self.assertNotIn("ALB", banks)

    def test_labels_come_from_the_value_list(self):
        from apps.core.lookups import clear_labels
        sub = receipt(self.w["teller"], self.w["rhb"], "10.00", "LABELTEST123")
        self.assertEqual(sub.payment_method_label, "Bank transfer")
        PaymentMethod.objects.filter(code="TRANSFER").update(name="Online transfer")
        clear_labels()
        self.assertEqual(sub.payment_method_label, "Online transfer")
