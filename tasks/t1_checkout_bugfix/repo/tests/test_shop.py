from shop.cart import Cart
from shop.money import to_cents, fmt


def test_fmt():
    assert fmt(1234) == "12.34"
    assert fmt(5) == "0.05"


def test_to_cents_simple():
    assert to_cents("12.50") == 1250


def test_to_cents_float_trap():
    assert to_cents("0.29") == 29


def test_basic_uk_cart():
    c = Cart("UK")
    c.add("A", 2, "10.00")
    t = c.totals()
    assert t == {"subtotal": 2000, "discount": 0, "taxable": 2000, "tax": 400, "total": 2400}


def test_tax_after_discount():
    c = Cart("UK")
    c.add("A", 1, "100.00")
    t = c.totals("SAVE10")
    assert t["discount"] == 1000
    assert t["tax"] == 1800
    assert t["total"] == 10800
