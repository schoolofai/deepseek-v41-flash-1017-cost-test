import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Event:
    ts: int        # unix seconds
    user: str
    path: str
    status: int
    ms: int


_LINE_RE = re.compile(r"^(\S+) user=(\S+) path=(\S+) status=(\d{3}) ms=(\d+)$")
_FAST_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})Z"
    r" user=(\S+) path=(\S+) status=([0-9]{3}) ms=([0-9]+)$"
)
_DAYS_IN_MONTH = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _epoch_seconds(year, month, day, hour, minute, second):
    """Seconds since the epoch for a valid UTC civil time."""
    if not 1 <= year <= 9999:
        raise ValueError("year out of range")
    if not 1 <= month <= 12:
        raise ValueError("month out of range")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
        raise ValueError("time out of range")
    max_day = _DAYS_IN_MONTH[month]
    if month == 2 and _is_leap(year):
        max_day = 29
    if not 1 <= day <= max_day:
        raise ValueError("day out of range")

    y = year - (month <= 2)
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468
    return days * 86400 + hour * 3600 + minute * 60 + second


def _parse_slow(line):
    m = _LINE_RE.match(line)
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    path = m.group(3).split("?")[0].rstrip("/") or "/"
    return Event(int(ts.timestamp()), m.group(2).lower(), path, int(m.group(4)), int(m.group(5)))


def _parse_stripped(line):
    m = _FAST_RE.match(line)
    if m:
        year, month, day, hour, minute, second = (
            int(m.group(1)),
            int(m.group(2)),
            int(m.group(3)),
            int(m.group(4)),
            int(m.group(5)),
            int(m.group(6)),
        )
        try:
            ts = _epoch_seconds(year, month, day, hour, minute, second)
        except ValueError:
            return None
        path = m.group(8).split("?")[0].rstrip("/") or "/"
        return Event(ts, m.group(7).lower(), path, int(m.group(9)), int(m.group(10)))
    return _parse_slow(line)


def parse_line(line: str):
    """Return an Event, or None for a malformed line."""
    return _parse_stripped(line.strip())


def parse_all(lines):
    events, skipped = [], 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        e = _parse_stripped(stripped)
        if e is None:
            skipped += 1
        else:
            events.append(e)
    return events, skipped
