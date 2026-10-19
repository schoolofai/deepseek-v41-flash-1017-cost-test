import re
from datetime import datetime, timezone
from typing import NamedTuple

_LINE = re.compile(r"^(\S+) user=(\S+) path=(\S+) status=(\d{3}) ms=(\d+)$")
# Canonical timestamps take this fast path; anything else (e.g. lowercase t/z,
# 1-digit fields, non-ASCII digits) falls back to strptime to keep its leniency.
_FAST_TS = re.compile(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)Z", re.ASCII)
_UTC = timezone.utc
_FMT = "%Y-%m-%dT%H:%M:%SZ"


class Event(NamedTuple):
    ts: int        # unix seconds
    user: str
    path: str
    status: int
    ms: int


def _parse_ts(s):
    """Return unix seconds, or None if the timestamp is invalid."""
    m = _FAST_TS.fullmatch(s)
    try:
        if m:
            y, mo, d, h, mi, sec = map(int, m.groups())
            dt = datetime(y, mo, d, h, mi, sec, tzinfo=_UTC)
        else:
            dt = datetime.strptime(s, _FMT).replace(tzinfo=_UTC)
    except ValueError:
        return None
    return int(dt.timestamp())


def _parse_stripped(line: str):
    m = _LINE.match(line)
    if not m:
        return None
    ts = _parse_ts(m.group(1))
    if ts is None:
        return None
    path = m.group(3).split("?")[0].rstrip("/") or "/"
    return Event(ts, m.group(2).lower(), path, int(m.group(4)), int(m.group(5)))


def parse_line(line: str):
    """Return an Event, or None for a malformed line."""
    return _parse_stripped(line.strip())


def parse_all(lines):
    events, skipped = [], 0
    append = events.append
    for line in lines:
        line = line.strip()
        if not line:
            continue
        e = _parse_stripped(line)
        if e is None:
            skipped += 1
        else:
            append(e)
    return events, skipped
