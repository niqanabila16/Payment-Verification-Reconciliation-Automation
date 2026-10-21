"""Shared helpers for the test suites (not used at runtime)."""
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import hashlib

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import Branch, Role, User
from apps.core.models import Bank
from apps.reconciliation.services.submissions import create_submission

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample_data"
PASSWORD = "Test-Pass-12345!"


def make_world():
    """Two branches and one user per role. The four banks and the dropdown values come from the data migrations."""
    cache.clear()
    kj = Branch.objects.create(code="KJ", name="Kajang")
    pj = Branch.objects.create(code="PJ", name="Petaling Jaya")
    banks = {code.lower(): Bank.objects.get(code=code) for code in ("RHB", "ALB", "PBB", "MBB")}
    users = {
        "admin": User.objects.create_user("admin@t.test", PASSWORD, name="Admin", role=Role.ADMIN),
        "finance": User.objects.create_user("finance@t.test", PASSWORD, name="Finance", role=Role.FINANCE),
        "teller": User.objects.create_user("teller@t.test", PASSWORD, name="Teller KJ", role=Role.TELLER, branch=kj),
        "teller2": User.objects.create_user("teller2@t.test", PASSWORD, name="Teller PJ", role=Role.TELLER, branch=pj),
    }
    return {"kj": kj, "pj": pj, **banks, **users}


def receipt(user, bank, amount, reference, sender="CUSTOMER ONE", entered_at=None, holder=None):
    """Create a Teller receipt through the real service (it also creates the match and tries to match straight away)."""
    sub, _ = create_submission(user=user, entered_at=entered_at, data={
        "client_uuid": uuid.uuid4(), "sender_name": sender, "account_holder_name": holder or sender, "relationship": "SELF",
        "bank": bank, "amount": Decimal(str(amount)), "bank_reference_no": reference, "payment_method_code": "TRANSFER",
        "transaction_at": timezone.now() - timedelta(hours=1)})
    sub.match.refresh_from_db()
    return sub


def csv_upload(rows, name="stmt.csv", account="1230009876543", date="30/09/2026"):
    """Build an in-memory bank statement CSV with the standard 4-line preamble."""
    header = "Description,Branch Code,Debit (RM),Credit (RM),Sender`s Name/ Beneficiary's Name,Reference 1/ Recipient`s Reference,Reference 2/ Other Payment Details,Bank Ref No."
    lines = [f"Balance of Account {account} / Mandiri - Cust Ac as at {date}", "", "Current Account", header]
    lines += [",".join(f'"{c}"' for c in row) for row in rows]
    return SimpleUploadedFile(name, ("\n".join(lines) + "\n").encode("utf-8"), content_type="text/csv")


def credit_row(reference, amount, name="CUSTOMER ONE", description="RPP INWARD INST TRF CR"):
    """An RHB credit row. For every description except DuitNow QR the matching reference is the Bank Ref No. (Excel prints it with a leading ')."""
    return [description, "'980", "", f"{amount}", f" {name}/", "/oce", "/", f"'{reference}"]


def qr_row(qr, amount, name="CUSTOMER ONE", ref_no=None):
    """An RHB "DUITNOW QR POS CR" row: the matching reference is the QR id at the end of Reference 1, not the Bank Ref No."""
    return ["DUITNOW QR POS CR", "'980", "", f"{amount}", f" {name}/ ALI/", f" RHBQR049318/20260925MBBEMYKL030O{qr}", "/DuitQR Mcht Transfer",
            f"'{ref_no or 'B' + qr}"]


def upload_statement(user, rows, bank=None, name="stmt.csv", **kwargs):
    """Run a full RHB upload (parse, store, match) synchronously. Returns the refreshed StatementImport."""
    from apps.reconciliation.services.importer import start_import

    data = csv_upload(rows, name=name, **kwargs).read()
    bank = bank or Bank.objects.get(code="RHB")
    imp = start_import(user=user, bank=bank, data=data, digest=hashlib.sha256(data).hexdigest(), file_name=name)
    imp.refresh_from_db()
    return imp


def generic_csv(lines, name="stmt.csv"):
    """A statement file of the generic banks (ALB / PBB / MBB): free lines first, then the header and rows."""
    return SimpleUploadedFile(name, ("\n".join(lines) + "\n").encode("utf-8"), content_type="text/csv")


def upload_generic(user, bank, lines, name="g.csv"):
    from apps.reconciliation.services.importer import start_import

    data = generic_csv(lines, name).read()
    imp = start_import(user=user, bank=bank, data=data, digest=hashlib.sha256(data).hexdigest(), file_name=name)
    imp.refresh_from_db()
    return imp


def xlsx_statement(rows, name="stmt.xlsx"):
    """An in-memory .xlsx whose rows are given as lists (values may be text or numbers)."""
    from io import BytesIO
    from openpyxl import Workbook

    book = Workbook()
    for row in rows:
        book.active.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# Layouts copied from real statements, with invented accounts, names and amounts.
ALB_XLSX = [
    ["Transaction History"], [], [], ["Date", "2026-10-07"], ["Account Number", "140000000001"], [], [],
    ["No", "Transaction Date", "Branch Name", "Transaction Description", "Reference 1", "Reference 2", "Recipient's Reference / Other Payment Details",
     "Cheque No", "Amount", "", "Balance"],
    ["", "", "", "", "", "", "", "", "Debit", "Credit", ""],
    ["1", "29/08/2026 07:30:49", "ELECTRONIC BANKING SERVICES", "DuitNow CR Trf CA", "Fund Transfer", "TESTER ONE/RPP260829000000001", "", "", "", "7000.00", "9000.00"],
    ["2", "28/08/2026 17:25:37", "JALAN IPOH", "CDM CA CSH DEP-W/O C", "", "", "", "", "", "2670.00", "2000.00"],
    ["3", "28/08/2026 12:12:10", "ELECTRONIC BANKING SERVICES", "IB2G CA Common Chrg", "AOB Monthly Charges", "AOBMC28082026000001", "", "", "30.00", "", "-670.00"],
    ["", "", "", "", "", "", "", "", 'Total Amount: ="30.00"', 'Total Amount: ="9670.00"', ""],
]
PBB_XLSX = [
    ["Account Number:", "3200000001"], ["Account Name:", "TEST COMPANY SDN BHD"], ["Account Type:", "ACE ENTERPRISE"],
    ["From Date:", "2026-10-01"], ["To Date:", "2026-10-07"], ["Available Balance:", "MYR 1000.00"], [],
    ["Transaction Type :", "All Transaction"],
    ["Trn. Date", "Cheque No/Ref No", "Transaction Description", "Debit Amount", "Credit Amount", "Reference 1", "Reference 2", "Reference 3",
     "Reference 4", "Reference 5", "Reference 6"],
    ["01/10/2026", "003153", "DEP-CASH", "", "2110", "", "", "", "", "", ""],
    ["01/10/2026", "000000", "SI CR", "", "1345.15", "FROM 3999XXXXXX   BRH 0000197", "", "", "", "", ""],
    ["02/10/2026", "000000", "SI CR", "", "1345.15", "FROM 3999XXXXXX   BRH 0000197", "", "", "", "", ""],
    ["05/10/2026", "338623", "DUITNOW TRSF CR", "", "22500", "TESTER TWO", "INV 2026-0042", "", "", "", ""],
]
MBB_XLSX = [
    ["Transaction Date", "Transaction Time", "Posting Date", "Processing Time", "Transaction Description", "Transaction Ref", "Debit", "Credit",
     "Source Code", "Teller ID", "Transaction Code", "End Balance", "Filler", "Branch/Channel", "Transaction Description 2",
     "Transaction Description 3", "Transaction Description 4", "Transaction Description 5", "Currency", "Expiry Date"],
    ["", "", "07-oct-2026 MY (UTC+08:00)", "02:34 MY (UTC+08:00)", "DR/CARD SALES M/N 1111111 DATED 06102026", "D17940610", "0", "820", "006 - Pos", "CBSX432S", "8300 - ", "0", "", "2977", "-", "-", "-", "-", "MYR", ""],
    ["", "", "07-oct-2026 MY (UTC+08:00)", "02:36 MY (UTC+08:00)", "DR/CARD SALES M/N 1111111 DATED 06102026", "D17940610", "8", "0", "011 - System", "CBSX432S", "BCHARGE - ", "0", "", "2981", "-", "-", "-", "-", "MYR", ""],
    ["", "", "07-oct-2026 MY (UTC+08:00)", "10:05 MY (UTC+08:00)", "0235104001          CIT COLLECTION 2", "551016800000", "0", "10284", "025 - Office", "CBSX4618", "CCRBEN1 - ", "0", "", "2502", "-", "-", "-", "-", "MYR", ""],
    ["", "", "07-oct-2026 MY (UTC+08:00)", "10:05 MY (UTC+08:00)", "0235105001          CIT COLLECTION 2", "551016800000", "0", "34110", "025 - Office", "CBSX4618", "CCRBEN1 - ", "0", "", "2502", "-", "-", "-", "-", "MYR", ""],
]
