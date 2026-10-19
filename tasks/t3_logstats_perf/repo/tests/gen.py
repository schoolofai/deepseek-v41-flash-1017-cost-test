import random


def make_lines(n, seed=1, users=300, paths=40):
    rnd = random.Random(seed)
    t0 = 1792368000  # 2026-10-19T00:00:00Z
    lines = []
    t = t0
    for i in range(n):
        t += rnd.choice([0, 1, 2, 5, 30, 300, 1801, 2400])
        u = f"U{rnd.randrange(users)}" if rnd.random() < 0.5 else f"u{rnd.randrange(users)}"
        p = f"/p{rnd.randrange(paths)}" + rnd.choice(["", "/", "?q=1"])
        st = rnd.choice([200, 200, 200, 201, 404, 500, 503])
        ms = rnd.randrange(1, 5000)
        import time as _t
        stamp = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(t))
        if rnd.random() < 0.01:
            lines.append("garbage " + str(i))
        elif rnd.random() < 0.005:
            lines.append("")
        else:
            lines.append(f"{stamp} user={u} path={p} status={st} ms={ms}")
    rnd.shuffle(lines)
    return lines
