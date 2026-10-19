"""Money helpers. All amounts are integer cents."""


def to_cents(amount: str) -> int:
    amount = amount.strip()
    if not amount:
        raise ValueError("empty amount")
    if "." in amount and len(amount.split(".")[1]) > 2:
        raise ValueError(f"too many decimals: {amount}")
    return int(float(amount) * 100)


def fmt(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def round_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    return int(numerator / denominator)
