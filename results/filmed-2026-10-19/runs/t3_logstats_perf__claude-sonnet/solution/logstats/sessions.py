SESSION_GAP = 30 * 60  # a gap of MORE than 30 minutes starts a new session


def _times_by_user(events):
    by_user = {}
    for e in events:
        try:
            by_user[e.user].append(e.ts)
        except KeyError:
            by_user[e.user] = [e.ts]
    for times in by_user.values():
        times.sort()
    return by_user


def sessions_per_user(events):
    """Return {user: number_of_sessions}."""
    result = {}
    for user, times in _times_by_user(events).items():
        # Quirk kept from the original: every event (including duplicates at the
        # same timestamp) that follows a gap > SESSION_GAP counts as a new session.
        count, lower, cur = 1, None, None
        for t in times:
            if t != cur:
                lower, cur = cur, t
            if lower is not None and t - lower > SESSION_GAP:
                count += 1
        result[user] = count
    return result


def longest_session_seconds(events):
    """Return {user: length in seconds of that user's longest session}."""
    by_user = _times_by_user(events)
    out = {}
    for u in sorted(by_user):
        times = by_user[u]
        best, start, prev = 0, times[0], times[0]
        for t in times:
            if t - prev > SESSION_GAP:
                start = t
            if t - start > best:
                best = t - start
            prev = t
        out[u] = best
    return out
