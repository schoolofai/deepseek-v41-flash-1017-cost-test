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


def parse_line(line: str):
    """Return an Event, or None for a malformed line."""
    pattern = re.compile(r"^(\S+) user=(\S+) path=(\S+) status=(\d{3}) ms=(\d+)$")
    m = pattern.match(line.strip())
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    path = m.group(3).split("?")[0].rstrip("/") or "/"
    return Event(int(ts.timestamp()), m.group(2).lower(), path, int(m.group(4)), int(m.group(5)))


def parse_all(lines):
    events, skipped = [], 0
    for line in lines:
        if not line.strip():
            continue
        e = parse_line(line)
        if e is None:
            skipped += 1
        else:
            events.append(e)
    return events, skipped
