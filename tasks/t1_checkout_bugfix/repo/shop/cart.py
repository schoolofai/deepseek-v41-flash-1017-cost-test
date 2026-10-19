from .money import to_cents
from .discounts import apply_discount
from .tax import tax_for


class Cart:
    def __init__(self, region: str):
        self.region = region
        self._lines = []  # [sku, qty, unit_cents]

    def add(self, sku: str, qty: int, unit_price: str) -> None:
        if qty < 1:
            raise ValueError("qty must be >= 1")
        self._lines.append([sku, qty, to_cents(unit_price)])

    def remove(self, sku: str, qty: int) -> None:
        for line in self._lines:
            if line[0] == sku:
                if qty > line[1]:
                    raise ValueError("removing more than present")
                line[1] -= qty
                return
        raise ValueError(f"no such sku {sku}")

    def lines(self):
        return [tuple(l) for l in self._lines]

    def subtotal(self) -> int:
        return sum(q * u for _, q, u in self._lines)

    def totals(self, code=None) -> dict:
        subtotal = self.subtotal()
        discount = apply_discount(subtotal, code)
        tax = tax_for(subtotal, self.region)
        taxable = subtotal - discount
        return {"subtotal": subtotal, "discount": discount, "taxable": taxable,
                "tax": tax, "total": taxable + tax}
