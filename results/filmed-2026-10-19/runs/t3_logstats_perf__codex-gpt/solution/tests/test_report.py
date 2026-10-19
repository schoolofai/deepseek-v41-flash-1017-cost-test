import time

import pytest

from logstats.parser import Event
from logstats.report import build_report, latency_by_path, percentile
from tests.gen import make_lines

LINES = [
    "2026-10-19T10:00:00Z user=alice path=/a status=200 ms=100",
    "2026-10-19T10:10:00Z user=Alice path=/a/ status=500 ms=300",
    "2026-10-19T10:50:00Z user=alice path=/b?x=1 status=200 ms=50",
    "2026-10-19T10:05:00Z user=bob path=/a status=404 ms=10",
    "not a log line",
    "",
]


def test_small_report():
    r = build_report(LINES)
    assert r["events"] == 4 and r["skipped"] == 1 and r["users"] == 2
    assert r["top_paths"] == [("/a", 3), ("/b", 1)]
    assert r["latency"]["/a"] == {"p50": 100, "p95": 300, "max": 300}
    assert r["error_rate"] == 0.25
    assert r["sessions"] == {"alice": 2, "bob": 1}
    assert r["longest_session_s"] == {"alice": 600, "bob": 0}


def test_perf_smoke():
    lines = make_lines(5_000)
    t = time.perf_counter()
    build_report(lines)
    assert time.perf_counter() - t < 0.5


def test_empty_report():
    assert build_report(iter(["", " \t", "garbage"])) == {
        "events": 0,
        "skipped": 1,
        "users": 0,
        "top_paths": [],
        "latency": {},
        "error_rate": 0.0,
        "sessions": {},
        "longest_session_s": {},
    }


@pytest.mark.parametrize("limit", [None, -10, -1, 0, 1, 2, 10])
def test_report_order_and_top_path_slice(limit):
    lines = [
        f"2026-10-19T10:00:00Z user={user} path={path} status=200 ms=1"
        for user, path in [("bob", "/b"), ("alice", "/a"), ("carol", "/c")]
    ]
    report = build_report(iter(lines), k=limit)
    assert report["top_paths"] == [("/a", 1), ("/b", 1), ("/c", 1)][:limit]
    assert list(report) == [
        "events", "skipped", "users", "top_paths", "latency", "error_rate", "sessions", "longest_session_s"
    ]
    assert list(report["latency"]) == ["/a", "/b", "/c"]
    assert list(report["latency"]["/a"]) == ["p50", "p95", "max"]
    assert list(report["sessions"]) == ["alice", "bob", "carol"]
    assert list(report["longest_session_s"]) == ["alice", "bob", "carol"]


@pytest.mark.parametrize("count", [1, 2, 3, 19, 20, 21, 99, 100, 101])
def test_latency_nearest_rank_boundaries(count):
    values = list(reversed(range(count)))
    events = [Event(0, "alice", "/", 200, value) for value in values]
    assert latency_by_path(events) == {
        "/": {"p50": percentile(values, 50), "p95": percentile(values, 95), "max": max(values)}
    }
