"""
Builds the demo bank statements in this folder (CSV and XLSX) with the exact layout the bank website produces:
row 1 = "Balance of Account ... as at <date>", row 2 = blank, row 3 = "Current Account", row 4 = headers.
Run:  python sample_data/build_samples.py
"""
import csv
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).parent
HEADERS = ["Description", "Branch Code", "Debit (RM)", "Credit (RM)", "Sender`s Name/ Beneficiary's Name",
           "Reference 1/ Recipient`s Reference", "Reference 2/ Other Payment Details", "Bank Ref No."]
ROW1 = "Balance of Account 1230009876543 / Mandiri - Cust Ac as at 30/09/2026"

# Expected result when the matching Teller receipts from `manage.py seed_demo` exist:
#   GFP: 2235277A1, 611380310M, 77881234, 4400712, 88123456 | Typo: 99120045 | Manual review: 55302211 | Not found: 90019001
ROWS = [
    ["RPP INWARD INST TRF CR", "0100", "", "150.00", "MOH HAIKAL", "2235277A1", "", "MB26093000001"],
    ["DUITNOW QR POS CR", "0100", "", "80.50", "SITI AMINAH", "", "", "MB26093000002"],
    ["RPP INWARD INST TRF CR", "0100", "", "1,200.00", "ALI BIN ABU", "611380310M", "REMIT", "MB26093000003"],
    ["CDM CASH DEPOSIT CR", "0200", "", "500.00", "NURUL HUDA", "77881234", "", "MB26093000004"],
    ["RPP INWARD INST TRF CR", "0100", "", "320.00", "TAN WEI MING", "99120045", "", "MB26093000005"],
    ["RPP INWARD INST TRF CR", "0100", "", "250.00", "LIM AH KOW", "55302211", "", "MB26093000006"],
    ["IBG CR", "0300", "", "980.00", "KUMAR S", "4400712", "", "MB26093000007"],
    ["RPP INWARD INST TRF CR", "0100", "", "150.00", "DEVI A/P RAJ", "8812 3456", "", "MB26093000008"],
    ["SERVICE CHARGE DR", "0100", "5.00", "", "", "", "", "MB26093000009"],
    ["RPP INWARD INST TRF CR", "0100", "", "60.00", "UNKNOWN PAYER", "1122334455", "", "MB26093000010"],
]


def build() -> None:
    with open(HERE / "mandiri_statement_2026-09-30.csv", "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([ROW1])
        writer.writerow([])
        writer.writerow(["Current Account"])
        writer.writerow(HEADERS)
        writer.writerows(ROWS)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append([ROW1]); sheet.append([]); sheet.append(["Current Account"]); sheet.append(HEADERS)
    for row in ROWS:
        sheet.append(row)
    workbook.save(HERE / "mandiri_statement_2026-09-30.xlsx")
    print("Sample statements written to", HERE)


if __name__ == "__main__":
    build()
