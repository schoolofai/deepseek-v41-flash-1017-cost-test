from .money import round_half_up

_PERCENT = {"SAVE10": (10, 0), "SAVE25": (25, 5000)}


def apply_discount(subtotal_cents: int, code) -> int:
    if not code:
        return 0
    code = code.upper()
    if code in _PERCENT:
        pct, minimum = _PERCENT[code]
        if subtotal_cents < minimum:
            return 0
        return round_half_up(subtotal_cents * pct, 100)
    if code == "FLAT5":
        return min(500, subtotal_cents)
    raise KeyError(code)
