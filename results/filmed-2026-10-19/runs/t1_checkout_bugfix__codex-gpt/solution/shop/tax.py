from .money import round_half_up

# rates in basis points (1/100 of a percent)
RATES_BP = {"UK": 2000, "DE": 1900, "US-CA": 725, "US-OR": 0}


def tax_for(cents: int, region: str) -> int:
    bp = RATES_BP[region.upper()]
    return round_half_up(cents * bp, 10000)
