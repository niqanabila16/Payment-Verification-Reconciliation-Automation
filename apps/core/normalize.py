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
