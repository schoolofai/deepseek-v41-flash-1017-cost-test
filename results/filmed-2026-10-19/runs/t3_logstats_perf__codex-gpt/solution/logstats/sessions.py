from collections import defaultdict
from itertools import groupby


SESSION_GAP = 30 * 60  # a gap of MORE than 30 minutes starts a new session


def session_statistics(events):
    """Compute both statistics, counting every duplicate event after a gap."""
    times_by_user = defaultdict(list)
    for event in events:
        times_by_user[event.user].append(event.ts)

    sessions = {user: 1 for user in times_by_user}
    longest = {}
    for user in sorted(times_by_user):
        times = sorted(times_by_user[user])
        best = 0
        start = previous = times[0]
        for timestamp, duplicates in groupby(times):
            if timestamp - previous > SESSION_GAP:
                sessions[user] += sum(1 for _ in duplicates)
                start = timestamp
            best = max(best, timestamp - start)
            previous = timestamp
        longest[user] = best
    return sessions, longest


def sessions_per_user(events):
    """Return {user: number_of_sessions}."""
    return session_statistics(events)[0]


def longest_session_seconds(events):
    """Return {user: length in seconds of that user's longest session}."""
    return session_statistics(events)[1]
