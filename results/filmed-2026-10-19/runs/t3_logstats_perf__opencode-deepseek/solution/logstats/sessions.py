SESSION_GAP = 30 * 60  # a gap of MORE than 30 minutes starts a new session


def _timestamps_by_user(events):
    by_user = {}
    for e in events:
        counts = by_user.get(e.user)
        if counts is None:
            by_user[e.user] = {e.ts: 1}
        else:
            counts[e.ts] = counts.get(e.ts, 0) + 1
    return by_user


def sessions_per_user(events):
    """Return {user: number_of_sessions}."""
    result = {}
    for user, counts in _timestamps_by_user(events).items():
        sessions = 1
        previous = None
        for ts in sorted(counts):
            if previous is not None and ts - previous > SESSION_GAP:
                sessions += counts[ts]
            previous = ts
        result[user] = sessions
    return result


def longest_session_seconds(events):
    """Return {user: length in seconds of that user's longest session}."""
    out = {}
    by_user = _timestamps_by_user(events)
    for user in sorted(by_user):
        best, start, previous = 0, None, None
        for ts in sorted(by_user[user]):
            if start is None:
                start = ts
            elif ts - previous > SESSION_GAP:
                start = ts
            length = ts - start
            if length > best:
                best = length
            previous = ts
        out[user] = best
    return out
