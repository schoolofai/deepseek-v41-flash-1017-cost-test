"""Money helpers. All amounts are integer cents."""

import re


def to_cents(amount: str) -> int:
    match = re.fullmatch(r"(-?)([0-9]+)(?:\.([0-9]{1,2}))?", amount)
    if match is None:
        raise ValueError(f"invalid amount: {amount}")
    sign, whole, fraction = match.groups()
    cents = int(whole) * 100 + int((fraction or "").ljust(2, "0"))
    return -cents if sign else cents


def fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    quotient, remainder = divmod(abs(numerator), abs(denominator))
    if remainder * 2 >= abs(denominator):
        quotient += 1
    return -quotient if (numerator < 0) != (denominator < 0) else quotient
