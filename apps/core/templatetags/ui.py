"""Template helpers: icons, status badges, money format and character-level diff."""
import difflib
from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.core import lookups

register = template.Library()

# Status -> (label, css modifier, icon). Icon + text are always shown, so meaning never depends on colour alone.
STATUS_STYLES = {
    "pending": ("Pending", "warning", "clock"),
    "gfp": ("Verified (GFP)", "success", "check-circle"),
    "manual_review": ("Review", "review", "search"),
    "not_found": ("Not found", "neutral", "info"),
    "rejected": ("Reject", "danger", "x-circle"),
}


@register.simple_tag
def icon(name: str, css: str = "") -> str:
    """Render an icon from the inline SVG sprite (templates/components/icons.html)."""
    return format_html('<svg class="icon {}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>',
                       css, name)


@register.simple_tag
def status_badge(status: str) -> str:
    label, tone, icon_name = STATUS_STYLES.get(status, (status, "neutral", "info"))
    return format_html('<span class="badge badge--{}">{}<span>{}</span></span>',
                       tone, icon(icon_name), label)


@register.simple_tag
def match_badge(match) -> str:
    """Finance badge of a match; Review names the field that differs ("Review: amount differs")."""
    if match.match_status == "manual_review":
        return format_html('<span class="badge badge--review">{}<span>{}</span></span>', icon("search"), match.review_label)
    return status_badge(match.match_status)


@register.simple_tag
def teller_badge(status: str) -> str:
    """Tellers see Verified, Reject, or Pending for anything else."""
    return status_badge(status if status in ("gfp", "rejected") else "pending")


@register.filter
def payment_method_label(code: str) -> str:
    return lookups.label("payment_method", code)


@register.filter
def relationship_label(code: str) -> str:
    return lookups.label("relationship", code)


@register.filter
def status_label(status: str) -> str:
    return STATUS_STYLES.get(status, (status,))[0]


@register.filter
def money(value) -> str:
    """12345.5 -> 'RM 12,345.50'."""
    if value in (None, ""):
        return "-"
    return f"RM {Decimal(value):,.2f}"


@register.filter
def split_ref(value) -> list:
    """'Sherbeauty/RPP260828309298185/INARA GROUP SDN. BHD' -> ['Sherbeauty', 'RPP260828309298185', 'INARA GROUP SDN. BHD'].
    Every "/" in a bank reference separates a different value."""
    return [part.strip() for part in str(value or "").split("/") if part.strip()]


@register.simple_tag
def ref_diff(left: str, right: str) -> dict:
    """
    Character-level comparison of two references.
    Differing characters are wrapped in <mark class="chardiff"> so a one-digit typo is obvious.
    """
    left, right = left or "", right or ""
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    out_left, out_right = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            out_left.append(format_html("{}", left[i1:i2]))
            out_right.append(format_html("{}", right[j1:j2]))
            continue
        if i2 > i1:
            out_left.append(format_html('<mark class="chardiff">{}</mark>', left[i1:i2]))
        if j2 > j1:
            out_right.append(format_html('<mark class="chardiff">{}</mark>', right[j1:j2]))
    return {"left": mark_safe("".join(out_left)), "right": mark_safe("".join(out_right)),
            "same": left == right}

# ---- card dashboard helpers (templates/cards/_dashboard.html) -------------------------------------------------------
@register.filter
def branch_key(branch: dict, field: str) -> str:
    """The id the live refresh uses to find a number: b<branch id>.<field>."""
    return f"b{branch['id']}.{field}"


@register.filter
def dash_value(value, empty):
    """A branch that never received a card shows "-" instead of zeros."""
    return "-" if empty else value
