import time

from logstats.report import build_report
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
