"""Hidden acceptance tests: exact equivalence with the original implementation + speed."""
import importlib.util
import pathlib
import sys
import time

import pytest

from logstats.report import build_report

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from hidden_gen import make_lines  # noqa: E402
from oracle_pkg import report as oracle_report  # noqa: E402

QUIRKS = [
    "2026-10-19T10:00:00Z user=amy path=/x status=200 ms=5",
    "2026-10-19T11:00:00Z user=amy path=/x status=200 ms=6",
    "2026-10-19T11:00:00Z user=AMY path=/x/ status=503 ms=7",   # duplicate ts after a gap
    "2026-10-19T11:30:00Z user=amy path=/ status=200 ms=8",      # exactly 30 min: same session
    "2026-10-19T11:30:00Z user=amy path=/?a=b status=200 ms=8",
    "2026-10-19T12:00:01Z user=amy path=/y status=200 ms=9",     # 30 min + 1 s: new session
    "2026-10-19T25:00:00Z user=amy path=/y status=200 ms=9",     # bad hour -> skipped
    "2026-10-19T10:00:00Z user=bo path=/z status=99 ms=1",       # 2-digit status -> skipped
    "   ",
    "2026-10-19T10:00:00Z user=bo path=/z status=200 ms=1",
    "2026-10-19T10:00:00Z user=bo path=/z status=200 ms=1",
]


def test_quirks_match_original():
    assert build_report(QUIRKS) == oracle_report.build_report(QUIRKS)


def test_empty_input():
    assert build_report([]) == oracle_report.build_report([])
    assert build_report(["junk"]) == oracle_report.build_report(["junk"])


@pytest.mark.parametrize("seed,n,users,paths", [(7, 3000, 40, 9), (8, 3000, 5, 3), (9, 4000, 400, 60), (10, 2500, 2, 2)])
def test_random_equivalence(seed, n, users, paths):
    lines = make_lines(n, seed=seed, users=users, paths=paths)
    for k in (1, 5, 50):
        assert build_report(lines, k) == oracle_report.build_report(lines, k)


def test_dense_duplicates_equivalence():
    lines = make_lines(3000, seed=11, users=3, paths=4, dup_heavy=True)
    assert build_report(lines) == oracle_report.build_report(lines)


def test_speed_200k():
    lines = make_lines(200_000, seed=42, users=3000, paths=500)
    t = time.perf_counter()
    build_report(lines)
    elapsed = time.perf_counter() - t
    # PERF.md asks for well under 3 s; the extra 1 s is slack for machine noise
    assert elapsed < 4.0, f"took {elapsed:.2f}s"
