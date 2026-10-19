import re
from dataclasses import dataclass
from datetime import datetime, timezone


_LINE_PATTERN = re.compile(r"^(\S+) user=(\S+) path=(\S+) status=(\d{3}) ms=(\d+)$")
_CANONICAL_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


@dataclass(frozen=True)
class Event:
    ts: int        # unix seconds
    user: str
    path: str
    status: int
    ms: int


def parse_line(line: str):
    """Return an Event, or None for a malformed line."""
    match = _LINE_PATTERN.match(line.strip())
    if not match:
        return None
    stamp = match.group(1)
    try:
        if _CANONICAL_TIMESTAMP.fullmatch(stamp):
            ts = datetime.fromisoformat(stamp[:-1])
        else:
            ts = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
        ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    path = match.group(3).split("?")[0].rstrip("/") or "/"
    return Event(int(ts.timestamp()), match.group(2).lower(), path, int(match.group(4)), int(match.group(5)))


def parse_all(lines):
    events, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        event = parse_line(line)
        if event is None:
            skipped += 1
        else:
            events.append(event)
    return events, skipped
