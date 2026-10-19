import random

import pytest

from logstats.parser import Event
from logstats.sessions import longest_session_seconds, sessions_per_user


@pytest.mark.parametrize(
    ("times", "sessions", "longest"),
    [
        ([], 0, 0),
        ([0, 0, 0], 1, 0),
        ([1801, 0, 1801], 3, 0),
        ([0, 1800, 3600], 1, 3600),
        ([0, 1800, 3601], 2, 1800),
        ([1801, 0, 1801, 3601, 5402, 5402], 5, 1800),
        ([-1801, 0, 0], 3, 0),
        ([0, 1801, 1801, 1802, 3602], 3, 1801),
    ],
)
def test_session_gaps_and_duplicate_timestamps(times, sessions, longest):
    events = [Event(timestamp, "alice", "/", 200, 0) for timestamp in times]
    original = events.copy()
    assert sessions_per_user(events) == ({"alice": sessions} if times else {})
    assert longest_session_seconds(events) == ({"alice": longest} if times else {})
    assert events == original


def test_session_dictionary_order():
    events = [Event(0, user, "/", 200, 0) for user in ["bob", "alice", "carol", "bob"]]
    assert list(sessions_per_user(events)) == ["bob", "alice", "carol"]
    assert list(longest_session_seconds(events)) == ["alice", "bob", "carol"]


def test_session_counts_match_strictly_earlier_definition():
    randomizer = random.Random(42)
    timestamps = [-3602, -1801, -1, 0, 1, 1800, 1801, 3601, 5402]
    for _ in range(100):
        events = [
            Event(randomizer.choice(timestamps), randomizer.choice(["a", "b", "c"]), "/", 200, 0)
            for _ in range(randomizer.randrange(50))
        ]
        expected = {event.user: 1 for event in events}
        for event in events:
            earlier = [other.ts for other in events if other.user == event.user and other.ts < event.ts]
            if earlier and event.ts - max(earlier) > 1800:
                expected[event.user] += 1
        assert list(sessions_per_user(events).items()) == list(expected.items())
