import pytest

from logstats.parser import Event, parse_all, parse_line


@pytest.mark.parametrize(
    ("stamp", "timestamp"),
    [
        ("2026-10-19T10:00:00Z", 1792404000),
        ("2026-10-19t10:00:00z", 1792404000),
        ("2026-1-2T3:4:5Z", 1767323045),
        ("２０２６-10-19T10:00:00Z", 1792404000),
        ("1969-12-31T23:59:59Z", -1),
        ("0001-01-01T00:00:00Z", -62135596800),
        ("9999-12-31T23:59:59Z", 253402300799),
        ("2024-02-29T00:00:00Z", 1709164800),
    ],
)
def test_accepted_timestamps_and_unicode_normalization(stamp, timestamp):
    line = f"\t{stamp} user=İ path=/A///?q=1 status=５００ ms=٠\u2003"
    assert parse_line(line) == Event(timestamp, "i̇", "/A", 500, 0)


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-10-19T10:00:00.000Z",
        "2026-10-19T10:00:00+00:00",
        "20261019T10:00:00Z",
        "2026-W43-1T10:00:00Z",
        "2026-10-19X10:00:00Z",
        "2026-02-29T00:00:00Z",
        "2026-04-31T00:00:00Z",
        "2026-13-01T00:00:00Z",
        "2026-10-19T24:00:00Z",
        "2026-10-19T10:60:00Z",
        "2026-10-19T10:00:60Z",
        "0000-01-01T00:00:00Z",
        "10000-01-01T00:00:00Z",
    ],
)
def test_rejected_timestamps(stamp):
    assert parse_line(f"{stamp} user=alice path=/ status=200 ms=1") is None


@pytest.mark.parametrize(
    ("path", "expected"),
    [("?q=1", "/"), ("///", "/"), ("/a//b//?q=1", "/a//b"), ("a", "a")],
)
def test_path_normalization(path, expected):
    event = parse_line(f"2026-10-19T10:00:00Z user=ALICE path={path} status=200 ms=0")
    assert event.path == expected


@pytest.mark.parametrize(
    "fields",
    [
        "user=alice  path=/ status=200 ms=1",
        "user=alice\tpath=/ status=200 ms=1",
        "user=alice path=/ status=20 ms=1",
        "user=alice path=/ status=2000 ms=1",
        "user=alice path=/ status=200 ms=-1",
        "user=alice path=/ status=200 ms=+1",
        "user=alice path=/ status=200 ms=1.0",
        "user=alice path=/ status=200 ms=1 extra",
    ],
)
def test_rejected_fields(fields):
    assert parse_line(f"2026-10-19T10:00:00Z {fields}") is None


def test_blank_lines_are_not_skipped_lines():
    valid = "2026-10-19T10:00:00Z user=alice path=/ status=200 ms=1"
    lines = ["", " \t\n", "\u2003", "garbage", "\ufeff", valid]
    assert parse_all(iter(lines)) == ([parse_line(valid)], 2)
