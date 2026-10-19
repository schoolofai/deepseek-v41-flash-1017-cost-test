from collections import Counter, defaultdict

from .parser import parse_all
from .sessions import session_statistics


def percentile(values, pct):
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    rank = -(-pct * len(ordered) // 100)  # ceil
    return ordered[max(rank, 1) - 1]


def top_paths(events, k=5):
    counts = Counter(event.path for event in events)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:k]


def latency_by_path(events):
    latencies = defaultdict(list)
    for event in events:
        latencies[event.path].append(event.ms)
    out = {}
    for path in sorted(latencies):
        ordered = sorted(latencies[path])
        count = len(ordered)
        out[path] = {
            "p50": ordered[(count - 1) // 2],
            "p95": ordered[(95 * count + 99) // 100 - 1],
            "max": ordered[-1],
        }
    return out


def error_rate(events):
    if not events:
        return 0.0
    errors = sum(event.status >= 500 for event in events)
    return round(errors / len(events), 4)


def build_report(lines, k=5):
    events, skipped = parse_all(lines)
    sessions, longest_sessions = session_statistics(events)
    return {
        "events": len(events),
        "skipped": skipped,
        "users": len(sessions),
        "top_paths": top_paths(events, k),
        "latency": latency_by_path(events),
        "error_rate": error_rate(events),
        "sessions": dict(sorted(sessions.items())),
        "longest_session_s": longest_sessions,
    }
