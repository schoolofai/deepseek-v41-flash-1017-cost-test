# shop — checkout totals spec

All money is handled as integer **cents**. Never use floats for money.

## money.py
- `to_cents("12.34") -> 1234`. Accepts an optional leading `-`, up to 2 decimal places
  (`"5" -> 500`, `"5.5" -> 550`, `"0.29" -> 29`). More than 2 decimals or junk -> `ValueError`.
- `fmt(1234) -> "12.34"`, `fmt(-5) -> "-0.05"`.
- `round_half_up(numerator, denominator) -> int`: integer division rounded half away from zero.

## discounts.py
- `apply_discount(subtotal_cents, code) -> discount_cents` (a non-negative amount to subtract).
- Codes are case-insensitive. `None` or `""` -> 0.
- `SAVE10`: 10% of subtotal, rounded half up to the cent.
- `SAVE25`: 25% of subtotal, rounded half up, only when subtotal >= 5000 (50.00); otherwise 0.
- `FLAT5`: 500 cents off, but never more than the subtotal.
- Unknown code -> `KeyError`.

## tax.py
- `tax_for(cents, region) -> tax_cents`, rounded half up.
- Regions (case-insensitive): `UK` 20%, `DE` 19%, `US-CA` 7.25%, `US-OR` 0%.
- Unknown region -> `KeyError`.

## cart.py
- `Cart(region)`; `add(sku, qty, unit_price_str)`; adding an existing SKU **merges** into one
  line (quantities add; the unit price must match, otherwise `ValueError`). `qty` must be >= 1.
- `remove(sku, qty)` lowers the quantity; a line that reaches 0 disappears; removing more than
  present -> `ValueError`.
- `lines()` returns `[(sku, qty, unit_cents)]` in first-added order.
- `totals(code=None)` returns a dict with `subtotal`, `discount`, `taxable`, `tax`, `total` (cents):
  `taxable = subtotal - discount`; tax is charged on `taxable` (after the discount);
  `total = taxable + tax`.
