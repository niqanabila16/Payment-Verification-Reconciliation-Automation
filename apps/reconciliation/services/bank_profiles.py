"""
Bank statement layouts ("profiles"), one per bank category: RHB, ALB, PBB, MBB.

A profile says where the header row is, which header texts mean what and which transaction descriptions are reconciled.
Header texts are compared after removing case, spaces and punctuation, so "Sender`s Name/ Beneficiary's Name" and
"senders name beneficiarys name" are the same column.

ONLY the columns named in the profile are read (name, amount, reference, description, date). Every other column of the
bank file is ignored (revision 2, point 14): matching never looks at the rest of the row.

  RHB  name = "Sender`s Name/ Beneficiary's Name" (part before the first "/"), amount = Credit or Debit,
       reference = "QR<digits>" from "Reference 1/ Recipient`s Reference" when Description is "DUITNOW QR POS CR",
       otherwise "Bank Ref No.". Every row is reconciled.
  ALB  name + reference = "Reference 2" ("NAME/REFERENCE[/other]"), amount = Credit or Debit (under one "Amount" cell).
       Only "DuitNow CR Trf CA" rows are reconciled; the other rows are Open Items straight away.
  PBB  name = "Reference 1", reference = "Cheque No/Ref No", amount = Debit Amount or Credit Amount.
       Only "DUITNOW TRSF CR" rows are reconciled; the other rows are Open Items straight away.
  MBB  generic reader (no printed name): reference = "Transaction Ref". Unchanged from revision 1.

If a file is not read correctly, run `python manage.py inspect_statement <file> <bank>` to see what the reader understood,
then add the missing header text to the right alias set below.
"""
import re
from dataclasses import dataclass
from typing import Callable


def key(text) -> str:
    """Header comparison form: lower case letters and digits only."""
    return re.sub(r"[^0-9a-z]", "", str(text or "").lower())


def squash(text) -> str:
    """Collapse runs of whitespace (bank cells are often padded)."""
    return " ".join(str(text or "").split())


def description_key(text) -> str:
    """Comparison form of a transaction description: upper case, single spaces."""
    return squash(text).upper()


# ---- header aliases ---------------------------------------------------------------------------------------------
GENERIC_ALIASES = {
    "date": {"date", "transactiondate", "txndate", "trandate", "trndate", "transdate", "postingdate", "postdate", "valuedate", "tarikh", "tarikhtransaksi"},
    "description": {"description", "transactiondescription", "transactiondetails", "transactionnarrative", "details", "particulars",
                    "narrative", "remarks", "butiran", "paymentdetails", "transactiontype"},
    "debit": {"debit", "debitrm", "debitmyr", "debitamount", "withdrawal", "withdrawals", "withdrawalrm", "dr"},
    "credit": {"credit", "creditrm", "creditmyr", "creditamount", "deposit", "deposits", "depositrm", "cr"},
    "amount": {"amount", "amountrm", "amountmyr", "transactionamount", "txnamount"},
    "balance": {"balance", "balancerm", "runningbalance", "ledgerbalance", "closingbalance", "availablebalance", "baki"},
    "name": {"name", "sendername", "sendersname", "beneficiaryname", "beneficiarysname", "payername", "payeename", "counterparty",
             "sendersnamebeneficiarysname", "sendernamebeneficiaryname"},
    "reference_1": {"reference", "reference1", "ref", "ref1", "referenceno", "refno", "referencenumber", "chequeno", "chequenumber",
                    "paymentreference", "customerreference", "recipientsreference", "reference1recipientsreference"},
    "reference_2": {"reference2", "ref2", "otherpaymentdetails", "reference2otherpaymentdetails", "additionalreference", "otherreference"},
    "bank_ref_no": {"bankrefno", "bankreferenceno", "bankreference", "transactionreference", "transactionid", "txnid", "transactionrefno",
                    "serialno", "serialnumber"},
}

RHB_ALIASES = {
    "description": {"description"},
    "debit": {"debitrm", "debit"},
    "credit": {"creditrm", "credit"},
    "name": {"sendersnamebeneficiarysname", "sendernamebeneficiaryname", "sendersname", "beneficiarysname"},
    "reference_1": {"reference1recipientsreference", "reference1"},
    "bank_ref_no": {"bankrefno", "bankreferenceno", "bankreference"},
}

ALB_ALIASES = {
    "date": {"transactiondate"},
    "description": {"transactiondescription"},
    "amount": {"amount"},                      # "Debit" / "Credit" sit in the row below it (see parser._split_amount_header)
    "reference_2": {"reference2"},             # "NAME/REFERENCE[/other]": name and reference both come from here
}

PBB_ALIASES = {
    "date": {"trndate"},
    "description": {"transactiondescription"},
    "debit": {"debitamount"},
    "credit": {"creditamount"},
    "name": {"reference1"},                    # PBB prints the account holder in "Reference 1"
    "reference_1": {"chequenorefno"},          # "Cheque No/Ref No" is the reference
}

# MBB: "Transaction Ref" repeats (all rows of one cash-in-transit collection share it), so it is a reference, never a row key.
MBB_ALIASES = {**GENERIC_ALIASES, "reference_1": GENERIC_ALIASES["reference_1"] | {"transactionref"}}

AMOUNT_GROUP = ("debit", "credit", "amount")
TEXT_GROUP = ("description", "reference_1", "reference_2", "bank_ref_no")
FIELD_LABELS = {"description": "Description", "debit": "Debit", "credit": "Credit", "amount": "Amount", "bank_ref_no": "Bank Ref No.",
                "reference_1": "Reference", "reference_2": "Reference 2", "date": "Date"}


# ---- bank detection (used to catch "RHB selected but the file is ALB") ---------------------------------------------
def _preamble_text(rows: list[list[str]]) -> str:
    return key(" ".join(" ".join(r) for r in rows[:15]))


def _is_rhb(rows):
    if len(rows) < 4:
        return False
    header = {key(c) for c in rows[3]}
    return "bankrefno" in header and "branchcode" in header


def _keyword(*words):
    return lambda rows: any(w in _preamble_text(rows) for w in words)


def _headers(*names):
    """True when one of the first 60 rows contains all of these column titles (the layout fingerprint of a bank)."""
    wanted = set(names)
    return lambda rows: any(wanted <= {key(c) for c in row} for row in rows[:60])


def _either(*checks):
    return lambda rows: any(check(rows) for check in checks)


@dataclass(frozen=True)
class BankProfile:
    key: str
    label: str
    header_row: int | None                     # 1-based fixed row, or None = search the first 60 rows
    aliases: dict
    signature: Callable[[list], bool]          # does this file look like this bank?
    fixed_layout: bool = False                 # RHB: rows 1-3 are preamble, row 1 holds account number and date (BR-3/4/5)
    name_required: bool = True                 # the name (account holder) is part of the match; False for banks that print none
    matchable: frozenset | None = None         # description_key() values that are reconciled; None = every row

    def is_matchable(self, description: str) -> bool:
        return self.matchable is None or description_key(description) in self.matchable


PROFILES = {
    "rhb": BankProfile("rhb", "RHB", 4, RHB_ALIASES, _is_rhb, fixed_layout=True),
    "alb": BankProfile("alb", "ALB", None, ALB_ALIASES,
                       _either(_headers("transactiondate", "branchname", "reference1", "reference2"), _keyword("alliancebank")),
                       matchable=frozenset({"DUITNOW CR TRF CA"})),
    "pbb": BankProfile("pbb", "PBB", None, PBB_ALIASES,
                       _either(_headers("trndate", "debitamount", "creditamount"), _keyword("publicbank", "pbebank", "pbenterprise")),
                       matchable=frozenset({"DUITNOW TRSF CR"})),
    "mbb": BankProfile("mbb", "MBB", None, MBB_ALIASES,
                       _either(_headers("postingdate", "processingtime", "tellerid"), _keyword("maybank", "malayanbanking", "m2e")),
                       name_required=False),
}


def detect_bank(rows: list[list[str]]) -> str | None:
    """The bank the file appears to be from, or None when it cannot be told (then the selected bank is trusted)."""
    if _is_rhb(rows):
        return "rhb"
    hits = [k for k, p in PROFILES.items() if k != "rhb" and p.signature(rows)]
    return hits[0] if len(hits) == 1 else None


def map_headers(header_row: list[str], profile: BankProfile) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, title in enumerate(header_row):
        normalized = key(title)
        for canonical, names in profile.aliases.items():
            if normalized in names and canonical not in mapping:
                mapping[canonical] = index
                break
    return mapping


def has_required(mapping: dict[str, int], profile: BankProfile) -> bool:
    if profile.fixed_layout:   # RHB needs all of these (same rule as before)
        return all(f in mapping for f in ("description", "debit", "credit", "bank_ref_no"))
    return any(f in mapping for f in AMOUNT_GROUP) and any(f in mapping for f in TEXT_GROUP)
