"""Text helpers shared by the parser, the Teller form and the matching engine."""
import re
from decimal import Decimal, InvalidOperation

_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")

def normalize_reference(value) -> str:
    """
    BR-2: compare references by their letters and digits only.

    Spaces, hyphens, dots, slashes and letter case are ignored, so
    "8812-3456", "8812 3456" and "88123456" are the same reference.
    Excel often turns numeric references into floats (611380310.0); that
    trailing ".0" is removed first.
    """
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    return _NON_ALNUM.sub("", text).upper()


def parse_amount(value) -> Decimal | None:
    """Parse "1,234.50" / "RM 1234.5" / 1234.5 into a 2-decimal Decimal. Empty -> None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("RM", "").replace("rm", "").strip()
    if text in {"", "-"}:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"'{value}' is not a valid amount") from exc


TELLER_AMOUNT = re.compile(r"^(\d+)(?:[.,](\d{1,2}))?$")


def parse_teller_amount(value) -> Decimal:
    """
    Amount typed by a Teller. The currency is always MYR, so a comma (or a dot) marks the SEN:
    "150,50" and "150.50" are both RM 150.50, and "150" is RM 150.00.
    There is no thousands separator ("1,200" is read as RM 1.20, never RM 1,200), so it is rejected
    when it has more than two decimals or several separators.
    """
    text = str(value or "").strip().upper().replace("RM", "").replace(" ", "")
    match = TELLER_AMOUNT.match(text)
    if not match:
        raise ValueError("Enter the amount in ringgit with sen after a comma, for example 150,50. Do not use thousands separators.")
    whole, sen = match.group(1), (match.group(2) or "0").ljust(2, "0")
    amount = Decimal(f"{int(whole)}.{sen}")
    if amount <= 0:
        raise ValueError("The amount must be greater than zero.")
    return amount
