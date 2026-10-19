SESSION_GAP = 30 * 60  # a gap of MORE than 30 minutes starts a new session


def sessions_per_user(events):
    """Return {user: number_of_sessions}."""
    result = {e.user: 1 for e in events}
    for e in events:
        earlier = [o for o in events if o.user == e.user and (o.ts < e.ts)]
        if not earlier:
            continue
        prev = max(o.ts for o in earlier)
        if e.ts - prev > SESSION_GAP:
            result[e.user] += 1
    return result


def longest_session_seconds(events):
    """Return {user: length in seconds of that user's longest session}."""
    out = {}
    users = sorted(set(e.user for e in events))
    for u in users:
        times = sorted(e.ts for e in events if e.user == u)
        best, start = 0, times[0]
        for i in range(1, len(times)):
            if times[i] - times[i - 1] > SESSION_GAP:
                start = times[i]
            best = max(best, times[i] - start)
        out[u] = best
    return out
