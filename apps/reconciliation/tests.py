"""Tests for parsing, matching rules (BR-1, BR-2, BR-6, BR-8, BR-10) and Finance review actions."""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import AuditLog, Notification
from apps.core.normalize import normalize_reference, parse_amount
from apps.core.testing import SAMPLE_DIR, credit_row, csv_upload, make_world, receipt

from .models import MatchStatus, ReconciliationMatch, StatementEntry, StatementImport
from .services import review
from .services.engine import run_matching
from .services.importer import DuplicateImportError, start_import
from .services.parser import StatementParseError, parse_statement


class NormalizeTests(TestCase):
    def test_br2_ignores_case_spaces_hyphens_dots(self):
        for raw in ("8812-3456", "8812 3456", "88.12.34.56", " 88123456 "):
            self.assertEqual(normalize_reference(raw), "88123456")
        self.assertEqual(normalize_reference("ab-12"), "AB12")

    def test_excel_float_reference(self):
        self.assertEqual(normalize_reference(611380310.0), "611380310")
        self.assertEqual(normalize_reference("611380310.0"), "611380310")

    def test_amount_parsing(self):
        self.assertEqual(parse_amount("1,200.5"), Decimal("1200.50"))
        self.assertIsNone(parse_amount(""))
        with self.assertRaises(ValueError):
            parse_amount("abc")


class ParserTests(TestCase):
    def test_sample_csv_and_xlsx_parse_identically(self):
        csv_result = parse_statement((SAMPLE_DIR / "mandiri_statement_2026-09-30.csv").read_bytes(), "a.csv")
        xlsx_result = parse_statement((SAMPLE_DIR / "mandiri_statement_2026-09-30.xlsx").read_bytes(), "a.xlsx")
        self.assertEqual(len(csv_result.rows), 10)
        self.assertEqual([r.bank_ref_no for r in csv_result.rows], [r.bank_ref_no for r in xlsx_result.rows])
        self.assertEqual(csv_result.account_number, "1230009876543")
        self.assertEqual(str(csv_result.statement_date), "2026-09-30")

    def test_br3_br4_br5_rows_1_and_3_ignored_header_on_row_4(self):
        parsed = parse_statement((SAMPLE_DIR / "mandiri_statement_2026-09-30.csv").read_bytes(), "a.csv")
        self.assertEqual(parsed.rows[0].source_row, 5)                 # first transaction sits on row 5
        self.assertNotIn("Current Account", [r.description for r in parsed.rows])

    def test_wrong_header_row_gives_actionable_error(self):
        bad = b"Balance of Account 1 / X as at 30/09/2026\n\n\nWrong,Header\n1,2\n"
        with self.assertRaisesMessage(StatementParseError, "Row 4 must contain the column headers"):
            parse_statement(bad, "x.csv")

    def test_unreadable_row1_asks_for_manual_details(self):
        bad = csv_upload([credit_row("REF123456", "10.00", "B1")]).read()
        bad = bad.replace(b"Balance of Account 1230009876543 / Mandiri - Cust Ac as at 30/09/2026", b"Some unexpected title")
        with self.assertRaisesMessage(StatementParseError, "Row 1"):
            parse_statement(bad, "x.csv")
        ok = parse_statement(bad, "x.csv", fallback_account="999", fallback_date=timezone.localdate())
        self.assertEqual(ok.account_number, "999")

    def test_duplicate_ref_inside_file_and_invalid_rows_are_reported(self):
        upload = csv_upload([credit_row("REF111111", "10.00", "B1"), credit_row("REF111111", "10.00", "B1"),
                             credit_row("REF222222", "abc", "B2"), credit_row("REF333333", "5.00", "")])
        parsed = parse_statement(upload.read(), "x.csv")
        self.assertEqual(len(parsed.rows), 1)
        self.assertEqual(parsed.duplicates_in_file, 1)
        self.assertEqual(len(parsed.skipped), 2)

    def test_unsupported_extension(self):
        with self.assertRaises(StatementParseError):
            parse_statement(b"x", "statement.pdf")


@override_settings(IMPORT_RUN_SYNC=True)
class EngineTests(TestCase):
    def setUp(self):
        self.w = make_world()

    def upload(self, rows, **kwargs):
        return start_import(user=self.w["finance"], bank=self.w["mandiri"], uploaded_file=csv_upload(rows, **kwargs))

    def status_of(self, sub):
        return ReconciliationMatch.objects.get(teller_submission=sub).match_status

    def test_full_demo_scenario(self):
        call_command("seed_demo", verbosity=0)
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.core.models import Bank
        upload = SimpleUploadedFile("s.csv", (SAMPLE_DIR / "mandiri_statement_2026-09-30.csv").read_bytes())
        imp = start_import(user=self.w["finance"], bank=Bank.objects.get(code="MANDIRI"), uploaded_file=upload)
        imp.refresh_from_db()
        self.assertEqual(imp.status, "processed")
        self.assertEqual({k: imp.result_summary[k] for k in ("gfp", "typo", "manual_review", "not_found")},
                         {"gfp": 5, "typo": 1, "manual_review": 1, "not_found": 1})

    def test_exact_match_is_gfp_and_teller_is_notified(self):
        sub = receipt(self.w["teller"], self.w["mandiri"], "150.00", "ref-1234 56")
        self.upload([credit_row("REF123456", "150.00", "B1")])
        self.assertEqual(self.status_of(sub), MatchStatus.GFP)
        self.assertTrue(Notification.objects.filter(recipient=self.w["teller"], type="result_gfp").exists())

    def test_br8_amount_difference_never_auto_verified(self):
        sub = receipt(self.w["teller"], self.w["mandiri"], "150.00", "REF123456")
        self.upload([credit_row("REF123456", "150.01", "B1")])          # one sen off
        match = ReconciliationMatch.objects.get(teller_submission=sub)
        self.assertEqual(match.match_status, MatchStatus.MANUAL_REVIEW)
        self.assertIsNone(match.bank_statement_entry)                    # only a suggestion, not a final link
        self.assertIsNotNone(match.suggested_bank_statement_entry)

    def test_typo_is_only_a_suggestion(self):
        sub = receipt(self.w["teller"], self.w["mandiri"], "320.00", "99120054")
        self.upload([credit_row("99120045", "320.00", "B1")])
        match = ReconciliationMatch.objects.get(teller_submission=sub)
        self.assertEqual(match.match_status, MatchStatus.TYPO)
        self.assertIsNone(match.bank_statement_entry)
        self.assertGreaterEqual(match.match_score, 80)

    def test_br6_every_receipt_gets_a_definite_outcome(self):
        sub = receipt(self.w["teller"], self.w["mandiri"], "10.00", "NOTHINGHERE")
        self.upload([credit_row("OTHER99999", "77.00", "B1")])
        self.assertEqual(self.status_of(sub), MatchStatus.NOT_FOUND)

    def test_bank_is_respected(self):
        sub = receipt(self.w["teller"], self.w["rhb"], "150.00", "REF123456")   # receipt says RHB, statement is Mandiri
        self.upload([credit_row("REF123456", "150.00", "B1")])
        self.assertEqual(self.status_of(sub), MatchStatus.NOT_FOUND)

    def test_one_bank_row_serves_only_one_receipt(self):
        a = receipt(self.w["teller"], self.w["mandiri"], "150.00", "REF123456", sender="A")
        b = receipt(self.w["teller2"], self.w["mandiri"], "150.00", "REF-123456", sender="B")   # same normalised ref
        self.upload([credit_row("REF123456", "150.00", "B1")])
        statuses = sorted([self.status_of(a), self.status_of(b)])
        self.assertEqual(statuses, [MatchStatus.GFP, MatchStatus.NOT_FOUND])

    def test_debit_rows_are_never_matched(self):
        sub = receipt(self.w["teller"], self.w["mandiri"], "5.00", "FEE1234567")
        self.upload([["SERVICE CHARGE DR", "0100", "5.00", "", "", "FEE1234567", "", "B1"]])
        self.assertEqual(self.status_of(sub), MatchStatus.NOT_FOUND)

    def test_br10_late_statement_still_matches_old_receipt(self):
        old = timezone.now() - timedelta(days=20)
        sub = receipt(self.w["teller"], self.w["mandiri"], "150.00", "REF123456", entered_at=old)
        self.upload([credit_row("OTHER99999", "1.00", "B1")], date="01/09/2026", account="111")
        self.assertEqual(self.status_of(sub), MatchStatus.NOT_FOUND)
        self.upload([credit_row("REF123456", "150.00", "B2")], date="20/09/2026", account="222")
        self.assertEqual(self.status_of(sub), MatchStatus.GFP)

    def test_engine_stops_retrying_after_the_window(self):
        old = timezone.now() - timedelta(days=40)
        sub = receipt(self.w["teller"], self.w["mandiri"], "150.00", "REF123456")
        ReconciliationMatch.objects.filter(teller_submission=sub).update(first_seen_at=old, match_status=MatchStatus.NOT_FOUND)
        self.upload([credit_row("REF123456", "150.00", "B1")])
        self.assertEqual(self.status_of(sub), MatchStatus.NOT_FOUND)     # aged: Finance must decide

    def test_br1_same_file_cannot_be_imported_twice(self):
        rows = [credit_row("REF123456", "150.00", "B1")]
        self.upload(rows)
        with self.assertRaisesMessage(DuplicateImportError, "already imported"):
            self.upload(rows)
        self.assertEqual(StatementImport.objects.count(), 1)

    def test_br1_same_statement_date_cannot_be_imported_twice(self):
        self.upload([credit_row("REF123456", "150.00", "B1")])
        with self.assertRaises(DuplicateImportError):
            self.upload([credit_row("REF999999", "9.00", "B9")])         # different content, same account + date

    def test_br1_overlapping_periods_do_not_duplicate_rows(self):
        self.upload([credit_row("REF123456", "150.00", "B1"), credit_row("REF222222", "20.00", "B2")], date="29/09/2026")
        imp = self.upload([credit_row("REF222222", "20.00", "B2"), credit_row("REF333333", "30.00", "B3")], date="30/09/2026")
        imp.refresh_from_db()
        self.assertEqual(imp.result_summary["rows_added"], 1)
        self.assertEqual(imp.result_summary["rows_skipped_overlap"], 1)
        self.assertEqual(StatementEntry.objects.count(), 3)

    def test_rerun_without_new_data_changes_nothing(self):
        receipt(self.w["teller"], self.w["mandiri"], "150.00", "REF123456")
        self.upload([credit_row("REF123456", "150.00", "B1")])
        summary = run_matching()
        self.assertEqual(summary.evaluated, 0)                           # verified items are left alone

    def test_failed_import_can_be_retried(self):
        rows = [credit_row("REF123456", "150.00", "B1")]
        imp = self.upload(rows)
        StatementImport.objects.filter(pk=imp.pk).update(status="failed")
        retry = self.upload(rows)
        retry.refresh_from_db()
        self.assertEqual(retry.status, "processed")


@override_settings(IMPORT_RUN_SYNC=True)
class ReviewTests(TestCase):
    def setUp(self):
        self.w = make_world()
        self.typo_sub = receipt(self.w["teller"], self.w["mandiri"], "320.00", "99120054")
        self.diff_sub = receipt(self.w["teller2"], self.w["mandiri"], "205.00", "55302211", sender="LIM")
        start_import(user=self.w["finance"], bank=self.w["mandiri"],
                     uploaded_file=csv_upload([credit_row("99120045", "320.00", "B1"), credit_row("55302211", "250.00", "B2")]))
        self.typo = ReconciliationMatch.objects.get(teller_submission=self.typo_sub)
        self.diff = ReconciliationMatch.objects.get(teller_submission=self.diff_sub)

    def test_confirm_typo_makes_final_match_and_notifies(self):
        review.confirm_suggestion(self.typo, self.w["finance"])
        self.typo.refresh_from_db()
        self.assertEqual(self.typo.match_status, MatchStatus.GFP)
        self.assertIsNotNone(self.typo.bank_statement_entry)
        self.assertTrue(AuditLog.objects.filter(action="match.confirmed", entity_id=self.typo.pk).exists())

    def test_confirming_an_amount_difference_requires_a_note(self):
        with self.assertRaises(review.ReviewError):
            review.confirm_suggestion(self.diff, self.w["finance"])
        review.confirm_suggestion(self.diff, self.w["finance"], note="Customer paid RM 45 extra for a fee.")
        self.diff.refresh_from_db()
        self.assertEqual(self.diff.match_status, MatchStatus.GFP)

    def test_confirm_twice_is_rejected(self):
        review.confirm_suggestion(self.typo, self.w["finance"])
        with self.assertRaises(review.ReviewError):
            review.confirm_suggestion(self.typo, self.w["finance"])

    def test_reject_requires_reason_and_returns_to_not_found(self):
        with self.assertRaises(review.ReviewError):
            review.reject_suggestion(self.typo, self.w["finance"], " ")
        review.reject_suggestion(self.typo, self.w["finance"], "Different customer")
        self.typo.refresh_from_db()
        self.assertEqual(self.typo.match_status, MatchStatus.NOT_FOUND)
        self.assertIsNone(self.typo.suggested_bank_statement_entry)

    def test_close_requires_reason(self):
        with self.assertRaises(review.ReviewError):
            review.close_match(self.diff, self.w["finance"], "short")
        review.close_match(self.diff, self.w["finance"], "Customer cancelled the payment.")
        self.diff.refresh_from_db()
        self.assertEqual(self.diff.match_status, MatchStatus.CLOSED)
        self.assertTrue(self.diff.closed_reason)

    def test_manual_link_needs_note_and_free_row(self):
        review.reject_suggestion(self.typo, self.w["finance"], "wrong")
        entry = StatementEntry.objects.get(bank_ref_no="B1")
        with self.assertRaises(review.ReviewError):
            review.link_manually(self.typo, self.w["finance"], entry.pk, "")
        review.link_manually(self.typo, self.w["finance"], entry.pk, "Verified by phone with customer")
        other = receipt(self.w["teller"], self.w["mandiri"], "320.00", "ZZZZ999999", sender="OTHER")
        other_match = ReconciliationMatch.objects.get(teller_submission=other)
        with self.assertRaisesMessage(review.ReviewError, "already linked"):
            review.link_manually(other_match, self.w["finance"], entry.pk, "try same row")

    def test_feedback_posts_comment_and_notifies_teller(self):
        review.send_feedback(self.typo, self.w["finance"], "Reference ends with 45")
        self.assertEqual(self.typo.comments.count(), 1)
        self.assertTrue(Notification.objects.filter(recipient=self.w["teller"], type="feedback").exists())

    def test_teller_correction_resets_and_rematches(self):
        data = {"sender_name": "CUSTOMER ONE", "account_holder_name": "CUSTOMER ONE", "relationship": "SELF",
                "bank": self.w["mandiri"], "amount": Decimal("320.00"), "bank_reference_no": "99120045", "payment_method_code": "TRANSFER"}
        review.correct_submission(self.typo, self.w["teller"], data)
        self.typo.refresh_from_db()
        self.assertEqual(self.typo.match_status, MatchStatus.PENDING)
        run_matching(match_ids=[self.typo.pk], quiet=True)
        self.typo.refresh_from_db()
        self.assertEqual(self.typo.match_status, MatchStatus.GFP)

    def test_correction_not_allowed_once_verified(self):
        review.confirm_suggestion(self.typo, self.w["finance"])
        with self.assertRaises(review.ReviewError):
            review.correct_submission(self.typo, self.w["teller"], {})

    def test_reassign_branch_notifies_new_branch(self):
        review.reassign_branch(self.typo, self.w["finance"], self.w["pj"])
        self.typo_sub.refresh_from_db()
        self.assertEqual(self.typo_sub.branch, self.w["pj"])
        self.assertTrue(Notification.objects.filter(recipient=self.w["teller2"], type="branch_reassigned").exists())


@override_settings(IMPORT_RUN_SYNC=True)
class MaintenanceTests(TestCase):
    def setUp(self):
        self.w = make_world()

    def test_queue_is_oldest_first(self):
        old = receipt(self.w["teller"], self.w["mandiri"], "10.00", "OLDREF12345", entered_at=timezone.now() - timedelta(days=3))
        new = receipt(self.w["teller"], self.w["mandiri"], "11.00", "NEWREF12345")
        ids = list(ReconciliationMatch.objects.values_list("teller_submission_id", flat=True))
        self.assertEqual(ids, [old.pk, new.pk])

    def test_recover_imports_marks_stuck_imports_failed_and_allows_retry(self):
        rows = [credit_row("REF123456", "150.00", "B1")]
        imp = start_import(user=self.w["finance"], bank=self.w["mandiri"], uploaded_file=csv_upload(rows))
        StatementImport.objects.filter(pk=imp.pk).update(status="processing", imported_at=timezone.now() - timedelta(hours=1))
        call_command("recover_imports", verbosity=0)
        imp.refresh_from_db()
        self.assertEqual(imp.status, "failed")
        again = start_import(user=self.w["finance"], bank=self.w["mandiri"], uploaded_file=csv_upload(rows))
        again.refresh_from_db()
        self.assertEqual(again.status, "processed")

    def test_all_user_facing_text_is_english(self):
        """BR-9: guard against Indonesian/Malay UI text slipping into templates or scripts."""
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        banned = ("tidak ", "silakan", "gagal", "simpan", "berhasil", "kirim ", "catatan", "pilih ", "belum ")
        offenders = []
        for folder, patterns in (("templates", ("*.html",)), ("static/js", ("*.js",))):
            for pattern in patterns:
                for path in (root / folder).rglob(pattern):
                    text = path.read_text(encoding="utf-8").lower()
                    offenders += [f"{path.name}: {word.strip()}" for word in banned if word in text]
        self.assertEqual(offenders, [])
