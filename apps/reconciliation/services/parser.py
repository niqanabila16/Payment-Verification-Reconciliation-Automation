"""
Bank statement parser (REQ-F-1.3, BR-3, BR-4, BR-5).

Expected layout of the file Finance downloads from the bank website:

    row 1  "Balance of Account <number> / Mandiri - Cust Ac as at <date>"   -> read for metadata (BR-3)
    row 2  (blank / ignored)
    row 3  "Current Account"                                               -> ignored (BR-4)
    row 4  column headers                                                  -> data starts here (BR-5)
    row 5+ transactions

Both CSV and XLSX are supported. Column headers are matched after removing case,
spaces and punctuation, so "Sender`s Name/ Beneficiary's Name" and
"senders name beneficiarys name" are the same column.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings

from apps.core.normalize import normalize_reference, parse_amount


class StatementParseError(Exception):
    """Raised with a user-readable message when the file cannot be used."""


# canonical field -> accepted normalized header names
HEADER_ALIASES = {
    "description": {"description"},
    "bank_branch_code": {"branchcode"},
    "debit": {"debitrm", "debit"},
    "credit": {"creditrm", "credit"},
    "counterparty_name": {"sendersnamebeneficiarysname", "sendernamebeneficiaryname", "sendersname", "beneficiarysname"},
    "reference_1": {"reference1recipientsreference", "reference1"},
    "reference_2": {"reference2otherpaymentdetails", "reference2"},
    "bank_ref_no": {"bankrefno", "bankreferenceno", "bankreference"},
}
REQUIRED_FIELDS = ("description", "debit", "credit", "bank_ref_no")
FIELD_LABELS = {
    "description": "Description", "debit": "Debit (RM)", "credit": "Credit (RM)",
    "bank_ref_no": "Bank Ref No.",
}
DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%y", "%d.%m.%Y")


@dataclass
class ParsedRow:
    source_row: int
    description: str
    bank_branch_code: str
    debit: Decimal | None
    credit: Decimal | None
    counterparty_name: str
    reference_1: str
    reference_2: str
    bank_ref_no: str
    reference_normalized: str


@dataclass
class ParsedStatement:
    account_number: str
    account_label: str
    statement_date: date
    file_format: str
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # human-readable reasons for rows we could not use
    duplicates_in_file: int = 0


def _key(text) -> str:
    return re.sub(r"[^0-9a-z]", "", str(text or "").lower())


def _cell(value) -> str:
    """Excel returns numbers as float/int/datetime; turn everything into clean text."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _read_rows(data: bytes, extension: str) -> list[list[str]]:
    if extension == ".xlsx":
        from openpyxl import load_workbook

        try:
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:
            raise StatementParseError("The XLSX file could not be opened. Make sure it is a valid Excel file "
                                      "downloaded from the bank and not password protected.") from exc
        sheet = workbook.worksheets[0]
        return [[_cell(c) for c in row] for row in sheet.iter_rows(values_only=True)]
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise StatementParseError("The CSV file uses an unknown text encoding. Re-download it from the bank website.")
    return [[_cell(c) for c in row] for row in csv.reader(io.StringIO(text))]


def _parse_metadata(row1: list[str]) -> tuple[str, str, date | None]:
    """Row 1: 'Balance of Account 1234567890 / Mandiri - Cust Ac as at 30/09/2026' (BR-3)."""
    text = " ".join(c for c in row1 if c)
    account = ""
    match = re.search(r"Account\s+([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if match:
        account = match.group(1)
    else:
        digits = re.search(r"\d{6,}", text)
        account = digits.group(0) if digits else ""
    when = None
    match = re.search(r"as at\s+(.+)$", text, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip().rstrip(".")
        for fmt in DATE_FORMATS:
            try:
                when = datetime.strptime(candidate, fmt).date()
                break
            except ValueError:
                continue
    label = text[:100]
    return account, label, when


def _map_headers(header_row: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, title in enumerate(header_row):
        normalized = _key(title)
        for canonical, aliases in HEADER_ALIASES.items():
            if normalized in aliases and canonical not in mapping:
                mapping[canonical] = index
    return mapping


def parse_statement(data: bytes, filename: str, fallback_account: str = "",
                    fallback_date: date | None = None) -> ParsedStatement:
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in settings.ALLOWED_STATEMENT_EXTENSIONS:
        raise StatementParseError("Unsupported file type. Upload the bank statement as a .csv or .xlsx file.")
    rows = _read_rows(data, extension)
    header_index = settings.STATEMENT_HEADER_ROW - 1
    if len(rows) <= header_index:
        raise StatementParseError(
            f"The file has only {len(rows)} row(s). A bank statement needs the header on row "
            f"{settings.STATEMENT_HEADER_ROW} followed by transactions.")

    account, label, when = _parse_metadata(rows[0])
    account = account or fallback_account.strip()
    when = when or fallback_date
    if not account or not when:
        raise StatementParseError(
            "Row 1 of the file could not be read for the account number or statement date. "
            "Expected text like 'Balance of Account 1234567890 / Mandiri - Cust Ac as at 30/09/2026'. "
            "Enter the account number and statement date manually in the upload form and try again.")

    mapping = _map_headers(rows[header_index])
    missing = [FIELD_LABELS[f] for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        raise StatementParseError(
            f"Row {settings.STATEMENT_HEADER_ROW} must contain the column headers, but these are missing: "
            f"{', '.join(missing)}. Check that rows 1-3 of the file are untouched and the header is on row "
            f"{settings.STATEMENT_HEADER_ROW}.")

    parsed = ParsedStatement(account_number=account, account_label=label, statement_date=when,
                             file_format=extension.lstrip("."))
    seen_refs: set[str] = set()

    def get(row: list[str], name: str) -> str:
        idx = mapping.get(name)
        return row[idx].strip() if idx is not None and idx < len(row) else ""

    for offset, row in enumerate(rows[header_index + 1:], start=settings.STATEMENT_HEADER_ROW + 1):
        if not any(row):
            continue  # blank line
        bank_ref = get(row, "bank_ref_no")
        try:
            debit, credit = parse_amount(get(row, "debit")), parse_amount(get(row, "credit"))
        except ValueError as exc:
            parsed.skipped.append(f"Row {offset}: {exc}.")
            continue
        if not bank_ref:
            parsed.skipped.append(f"Row {offset}: Bank Ref No. is empty.")
            continue
        if debit is None and credit is None:
            parsed.skipped.append(f"Row {offset}: neither Debit nor Credit has an amount.")
            continue
        if bank_ref in seen_refs:
            parsed.duplicates_in_file += 1
            continue
        seen_refs.add(bank_ref)
        ref1, ref2 = get(row, "reference_1"), get(row, "reference_2")
        parsed.rows.append(ParsedRow(
            source_row=offset, description=get(row, "description")[:100],
            bank_branch_code=get(row, "bank_branch_code")[:20], debit=debit, credit=credit,
            counterparty_name=get(row, "counterparty_name")[:150], reference_1=ref1[:150], reference_2=ref2[:150],
            bank_ref_no=bank_ref[:50],
            reference_normalized=(normalize_reference(ref1) or normalize_reference(ref2) or normalize_reference(bank_ref))[:150],
        ))
    if not parsed.rows:
        raise StatementParseError("No usable transactions were found below the header row.")
    return parsed
