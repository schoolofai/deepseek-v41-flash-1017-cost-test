import random
import time as _t


def make_lines(n, seed=1, users=300, paths=40, dup_heavy=False):
    rnd = random.Random(seed)
    t = 1792368000
    steps = [0, 0, 0, 1, 1800, 1801, 3600] if dup_heavy else [0, 1, 2, 5, 30, 300, 1800, 1801, 2400]
    lines = []
    for i in range(n):
        t += rnd.choice(steps)
        u = f"U{rnd.randrange(users)}" if rnd.random() < 0.5 else f"u{rnd.randrange(users)}"
        p = f"/p{rnd.randrange(paths)}" + rnd.choice(["", "/", "?q=1", "//"])
        st = rnd.choice([200, 200, 200, 201, 404, 500, 503])
        ms = rnd.randrange(1, 5000)
        stamp = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(t))
        r = rnd.random()
        if r < 0.01:
            lines.append("garbage " + str(i))
        elif r < 0.015:
            lines.append("")
        elif r < 0.02:
            lines.append(f"{stamp} user={u} path={p} status=2000 ms={ms}")
        else:
            lines.append(f"{stamp} user={u} path={p} status={st} ms={ms}")
    rnd.shuffle(lines)
    return lines
