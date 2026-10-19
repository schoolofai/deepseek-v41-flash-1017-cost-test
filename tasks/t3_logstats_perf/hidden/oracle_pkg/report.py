from .parser import parse_all
from .sessions import sessions_per_user, longest_session_seconds


def percentile(values, pct):
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    rank = -(-pct * len(ordered) // 100)  # ceil
    return ordered[max(rank, 1) - 1]


def top_paths(events, k=5):
    paths = [e.path for e in events]
    counts = []
    for p in set(paths):
        counts.append((p, paths.count(p)))
    counts.sort(key=lambda pc: (-pc[1], pc[0]))
    return counts[:k]


def latency_by_path(events):
    out = {}
    for p in sorted(set(e.path for e in events)):
        ms = [e.ms for e in events if e.path == p]
        out[p] = {"p50": percentile(ms, 50), "p95": percentile(ms, 95), "max": max(ms)}
    return out


def error_rate(events):
    if not events:
        return 0.0
    errors = len([e for e in events if e.status >= 500])
    return round(errors / len(events), 4)


def build_report(lines, k=5):
    events, skipped = parse_all(lines)
    return {
        "events": len(events),
        "skipped": skipped,
        "users": len(set(e.user for e in events)),
        "top_paths": top_paths(events, k),
        "latency": latency_by_path(events),
        "error_rate": error_rate(events),
        "sessions": dict(sorted(sessions_per_user(events).items())),
        "longest_session_s": longest_session_seconds(events),
    }
