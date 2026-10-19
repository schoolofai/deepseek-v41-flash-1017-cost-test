"""Money helpers. All amounts are integer cents."""
import re


def to_cents(amount: str) -> int:
    amount = amount.strip()
    if not amount:
        raise ValueError("empty amount")
    m = re.fullmatch(r"(-?)(\d+)(?:\.(\d{1,2}))?", amount, re.ASCII)
    if not m:
        raise ValueError(f"invalid amount: {amount!r}")
    sign, whole, frac = m.groups()
    cents = int(whole) * 100 + int((frac or "").ljust(2, "0"))
    return -cents if sign else cents


def fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    if denominator < 0:
        numerator, denominator = -numerator, -denominator
    sign = -1 if numerator < 0 else 1
    return sign * ((abs(numerator) * 2 + denominator) // (2 * denominator))
