"""Shared helpers for the test suites (not used at runtime)."""
import uuid
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import Branch, Role, User
from apps.core.models import Bank
from apps.reconciliation.services.submissions import create_submission

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"
PASSWORD = "Test-Pass-12345!"


def make_world():
    """Two branches, two banks and one user per role. Returns a simple namespace-like dict."""
    kj = Branch.objects.create(code="KJ", name="Kajang")
    pj = Branch.objects.create(code="PJ", name="Petaling Jaya")
    mandiri = Bank.objects.create(code="MANDIRI", name="Bank Mandiri")
    rhb = Bank.objects.create(code="RHB", name="RHB Bank")
    users = {
        "admin": User.objects.create_user("admin@t.test", PASSWORD, name="Admin", role=Role.ADMIN),
        "finance": User.objects.create_user("finance@t.test", PASSWORD, name="Finance", role=Role.FINANCE),
        "teller": User.objects.create_user("teller@t.test", PASSWORD, name="Teller KJ", role=Role.TELLER, branch=kj),
        "teller2": User.objects.create_user("teller2@t.test", PASSWORD, name="Teller PJ", role=Role.TELLER, branch=pj),
    }
    return {"kj": kj, "pj": pj, "mandiri": mandiri, "rhb": rhb, **users}


def receipt(user, bank, amount, reference, sender="CUSTOMER ONE", entered_at=None):
    """Create a Teller receipt through the real service (also creates its pending match)."""
    sub, _ = create_submission(user=user, entered_at=entered_at, data={
        "client_uuid": uuid.uuid4(), "sender_name": sender, "account_holder_name": sender, "relationship": "SELF",
        "bank": bank, "amount": Decimal(str(amount)), "bank_reference_no": reference, "payment_method_code": "TRANSFER"})
    return sub


def csv_upload(rows, name="stmt.csv", account="1230009876543", date="30/09/2026"):
    """Build an in-memory bank statement CSV with the standard 4-line preamble."""
    header = "Description,Branch Code,Debit (RM),Credit (RM),Sender`s Name/ Beneficiary's Name,Reference 1/ Recipient`s Reference,Reference 2/ Other Payment Details,Bank Ref No."
    lines = [f"Balance of Account {account} / Mandiri - Cust Ac as at {date}", "", "Current Account", header]
    lines += [",".join(f'"{c}"' for c in row) for row in rows]
    return SimpleUploadedFile(name, ("\n".join(lines) + "\n").encode("utf-8"), content_type="text/csv")


def credit_row(reference, amount, ref_no, name="PAYER", description="RPP INWARD INST TRF CR"):
    return [description, "0100", "", f"{amount}", name, reference, "", ref_no]
