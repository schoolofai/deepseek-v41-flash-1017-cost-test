import pytest
from shop.cart import Cart
from shop.money import to_cents, fmt, round_half_up
from shop.discounts import apply_discount
from shop.tax import tax_for


@pytest.mark.parametrize("s,c", [("0.29", 29), ("1.15", 115), ("4.35", 435), ("5", 500), ("5.5", 550),
                                 ("-2.01", -201), ("19.99", 1999), ("0.07", 7), ("1000000.01", 100000001)])
def test_to_cents_exact(s, c):
    assert to_cents(s) == c


@pytest.mark.parametrize("bad", ["1.234", "abc", "", "1.2.3", "--1"])
def test_to_cents_rejects(bad):
    with pytest.raises(ValueError):
        to_cents(bad)


def test_fmt_negative():
    assert fmt(-5) == "-0.05"


@pytest.mark.parametrize("n,d,r", [(5, 10, 1), (4, 10, 0), (15, 10, 2), (-5, 10, -1), (25, 100, 0), (50, 100, 1)])
def test_round_half_up(n, d, r):
    assert round_half_up(n, d) == r


def test_discount_rounding_half_up():
    assert apply_discount(1005, "SAVE10") == 101   # 100.5 -> 101
    assert apply_discount(1004, "save10") == 100


def test_save25_threshold():
    assert apply_discount(4999, "SAVE25") == 0
    assert apply_discount(5000, "SAVE25") == 1250
    assert apply_discount(5002, "Save25") == 1251  # 1250.5 -> 1251


def test_flat5_never_exceeds_subtotal():
    assert apply_discount(300, "FLAT5") == 300
    assert apply_discount(800, "flat5") == 500


def test_unknown_code():
    with pytest.raises(KeyError):
        apply_discount(1000, "FREE")


def test_tax_regions_case_insensitive():
    assert tax_for(1000, "uk") == 200
    assert tax_for(1000, "us-ca") == 73   # 72.5 -> 73
    assert tax_for(1000, "US-OR") == 0
    with pytest.raises(KeyError):
        tax_for(1000, "FR")


def test_merge_lines():
    c = Cart("DE")
    c.add("A", 1, "2.50")
    c.add("B", 1, "1.00")
    c.add("A", 2, "2.50")
    assert c.lines() == [("A", 3, 250), ("B", 1, 100)]
    with pytest.raises(ValueError):
        c.add("A", 1, "2.60")


def test_remove_to_zero_drops_line():
    c = Cart("UK")
    c.add("A", 2, "1.00")
    c.remove("A", 2)
    assert c.lines() == []
    c.add("B", 1, "1.00")
    with pytest.raises(ValueError):
        c.remove("B", 2)


def test_full_checkout_ca():
    c = Cart("US-CA")
    c.add("X", 3, "19.99")
    c.add("Y", 1, "0.29")
    c.add("X", 1, "19.99")
    t = c.totals("SAVE10")
    # subtotal 7996+29=8025; discount 802.5->803; taxable 7222; tax 7222*7.25%=523.595->524
    assert t == {"subtotal": 8025, "discount": 803, "taxable": 7222, "tax": 524, "total": 7746}


def test_flat5_small_cart_uk():
    c = Cart("uk")
    c.add("Z", 1, "3.00")
    t = c.totals("FLAT5")
    assert t == {"subtotal": 300, "discount": 300, "taxable": 0, "tax": 0, "total": 0}
