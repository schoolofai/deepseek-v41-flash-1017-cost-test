import pytest

from shop.cart import Cart
from shop.discounts import apply_discount
from shop.money import fmt, round_half_up, to_cents
from shop.tax import tax_for


@pytest.mark.parametrize(
    "amount, expected",
    [
        ("12.34", 1234),
        ("5", 500),
        ("5.5", 550),
        ("0", 0),
        ("-0.00", 0),
        ("-0.05", -5),
        ("-5.5", -550),
        ("-12", -1200),
        ("0005.50", 550),
        ("9007199254740993.99", 900719925474099399),
        ("-9007199254740993.99", -900719925474099399),
    ],
)
def test_to_cents(amount, expected):
    assert to_cents(amount) == expected


@pytest.mark.parametrize("cents", range(-100, 101))
def test_money_round_trip(cents):
    assert to_cents(fmt(cents)) == cents


@pytest.mark.parametrize(
    "amount",
    [
        "", "-", ".", ".50", "1.", "+1.00", " 1.00", "1.00 ", "1.00\n",
        "1e2", "NaN", "inf", "--1", "1.2.3", "1.234", "1_000", "junk",
    ],
)
def test_to_cents_rejects_invalid_amounts(amount):
    with pytest.raises(ValueError):
        to_cents(amount)


@pytest.mark.parametrize(
    "cents, expected",
    [(1234, "12.34"), (-5, "-0.05"), (-1234, "-12.34"), (0, "0.00")],
)
def test_fmt(cents, expected):
    assert fmt(cents) == expected


@pytest.mark.parametrize(
    "numerator, denominator, expected",
    [
        (0, 10, 0),
        (4, 10, 0),
        (5, 10, 1),
        (6, 10, 1),
        (15, 10, 2),
        (-4, 10, 0),
        (-5, 10, -1),
        (-6, 10, -1),
        (-15, 10, -2),
        (5, -10, -1),
        (-5, -10, 1),
        (6, 4, 2),
        (7, 3, 2),
        (8, 3, 3),
        (90071992547409935, 10, 9007199254740994),
        (-90071992547409935, 10, -9007199254740994),
    ],
)
def test_round_half_up(numerator, denominator, expected):
    assert round_half_up(numerator, denominator) == expected


def test_round_half_up_zero_denominator():
    with pytest.raises(ZeroDivisionError):
        round_half_up(1, 0)


@pytest.mark.parametrize(
    "subtotal, code, expected",
    [
        (10000, None, 0),
        (10000, "", 0),
        (10000, "SAVE10", 1000),
        (15, "save10", 2),
        (14, "SaVe10", 1),
        (4999, "SAVE25", 0),
        (5000, "save25", 1250),
        (5002, "SaVe25", 1251),
        (10000, "FLAT5", 500),
        (500, "flat5", 500),
        (499, "FlAt5", 499),
        (0, "FLAT5", 0),
        (-100, "SAVE10", 0),
        (-100, "SAVE25", 0),
        (-100, "FLAT5", 0),
    ],
)
def test_discounts(subtotal, code, expected):
    assert apply_discount(subtotal, code) == expected


def test_unknown_discount():
    with pytest.raises(KeyError):
        apply_discount(10000, "UNKNOWN")


@pytest.mark.parametrize(
    "cents, region, expected",
    [
        (10000, "UK", 2000),
        (3, "uk", 1),
        (10000, "DE", 1900),
        (50, "de", 10),
        (10000, "US-CA", 725),
        (200, "us-ca", 15),
        (10000, "US-OR", 0),
        (12345, "us-or", 0),
        (0, "UK", 0),
        (-200, "US-CA", -15),
    ],
)
def test_tax(cents, region, expected):
    assert tax_for(cents, region) == expected


def test_unknown_region():
    with pytest.raises(KeyError):
        tax_for(0, "UNKNOWN")


def test_cart_merges_skus_and_preserves_order():
    cart = Cart("UK")
    cart.add("B", 1, "5.00")
    cart.add("A", 2, "0.29")
    cart.add("B", 3, "5")
    assert cart.lines() == [("B", 4, 500), ("A", 2, 29)]
    assert cart.subtotal() == 2058


def test_cart_rejects_conflicting_prices_without_changing_lines():
    cart = Cart("UK")
    cart.add("A", 2, "5.00")
    with pytest.raises(ValueError):
        cart.add("A", 1, "6.00")
    assert cart.lines() == [("A", 2, 500)]


@pytest.mark.parametrize("qty", [0, -1])
def test_cart_rejects_invalid_quantities(qty):
    cart = Cart("UK")
    with pytest.raises(ValueError):
        cart.add("A", qty, "1.00")
    assert cart.lines() == []
    cart.add("A", 2, "1.00")
    with pytest.raises(ValueError):
        cart.remove("A", qty)
    assert cart.lines() == [("A", 2, 100)]


def test_cart_remove_and_readd():
    cart = Cart("UK")
    cart.add("A", 3, "5.00")
    cart.add("B", 1, "1.00")
    cart.remove("A", 1)
    assert cart.lines() == [("A", 2, 500), ("B", 1, 100)]
    cart.remove("A", 2)
    assert cart.lines() == [("B", 1, 100)]
    cart.add("A", 1, "6.00")
    assert cart.lines() == [("B", 1, 100), ("A", 1, 600)]
    cart.remove("B", 1)
    cart.remove("A", 1)
    assert cart.lines() == []
    assert cart.subtotal() == 0


def test_cart_rejects_invalid_removals_without_changing_lines():
    cart = Cart("UK")
    cart.add("A", 2, "5.00")
    with pytest.raises(ValueError):
        cart.remove("A", 3)
    with pytest.raises(ValueError):
        cart.remove("B", 1)
    assert cart.lines() == [("A", 2, 500)]


def test_lines_returns_a_snapshot():
    cart = Cart("UK")
    cart.add("A", 1, "1.00")
    snapshot = cart.lines()
    snapshot.append(("B", 1, 200))
    cart.add("A", 1, "1.00")
    assert snapshot == [("A", 1, 100), ("B", 1, 200)]
    assert cart.lines() == [("A", 2, 100)]


@pytest.mark.parametrize(
    "region, price, code, expected",
    [
        ("uk", "0.15", "save10", (15, 2, 13, 3, 16)),
        ("de", "50.02", "save25", (5002, 1251, 3751, 713, 4464)),
        ("us-ca", "7.00", "flat5", (700, 500, 200, 15, 215)),
        ("UK", "1.00", "FLAT5", (100, 100, 0, 0, 0)),
        ("US-OR", "10.00", None, (1000, 0, 1000, 0, 1000)),
    ],
)
def test_cart_totals(region, price, code, expected):
    cart = Cart(region)
    cart.add("A", 1, price)
    totals = dict(zip(("subtotal", "discount", "taxable", "tax", "total"), expected))
    assert cart.totals(code) == totals
    assert cart.totals(code) == totals
    assert cart.lines() == [("A", 1, to_cents(price))]


@pytest.mark.parametrize("code", [None, "", "SAVE10", "SAVE25", "FLAT5"])
def test_empty_cart(code):
    assert Cart("UK").totals(code) == {
        "subtotal": 0, "discount": 0, "taxable": 0, "tax": 0, "total": 0,
    }
