"""Money helpers. All amounts are integer cents."""

import re

_AMOUNT_RE = re.compile(r"^-?\d+(?:\.\d{1,2})?$")


def to_cents(amount: str) -> int:
    if not isinstance(amount, str):
        raise ValueError(f"invalid amount: {amount!r}")
    amount = amount.strip()
    if not _AMOUNT_RE.match(amount):
        raise ValueError(f"invalid amount: {amount!r}")
    negative = amount.startswith("-")
    if negative:
        amount = amount[1:]
    whole, _, fraction = amount.partition(".")
    fraction = (fraction + "00")[:2]
    cents = int(whole) * 100 + int(fraction)
    return -cents if negative else cents


def fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    if denominator == 0:
        raise ZeroDivisionError("division by zero")
    negative = (numerator < 0) != (denominator < 0)
    n, d = abs(numerator), abs(denominator)
    quotient, remainder = divmod(n, d)
    if remainder * 2 >= d:
        quotient += 1
    return -quotient if negative else quotient
