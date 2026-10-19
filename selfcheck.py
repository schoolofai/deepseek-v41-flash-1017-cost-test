#!/usr/bin/env python3
"""Self-check for the task repos (no network, no API, no key, $0).

For each task:
  1. starter repo -> the hidden tests must not all pass (there is real work to do)
  2. each filmed agent solution in results/filmed-2026-10-19/runs/<task>__<harness>/solution/ (if any)
     overlaid on the starter, with the ORIGINAL visible tests restored -> visible + hidden tests must ALL pass
The private reference solutions are not published; the agents' own solutions are the proof the tests can be passed.
"""
import json
import pathlib
import shutil
import sys
import tempfile

from scoring import run_pytest

ROOT = pathlib.Path(__file__).resolve().parent
TASKS = ROOT / "tasks"
RUNS = ROOT / "results" / "filmed-2026-10-19" / "runs"


def overlay(src: pathlib.Path, dst: pathlib.Path):
    for f in src.rglob("*"):
        if f.is_file() and f.relative_to(src).parts[0] != "tests":   # agents' own test edits are not used for scoring
            t = dst / f.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)


def score(task_dir, task, solution=None):
    with tempfile.TemporaryDirectory(prefix="selfcheck-") as tmp:
        ws = pathlib.Path(tmp) / "ws"
        shutil.copytree(task_dir / "repo", ws)
        if solution:
            overlay(solution, ws)
        vis = run_pytest(ws, ws / "tests", timeout_per_test=task.get("test_timeout_s", 60))
        hid = run_pytest(ws, task_dir / "hidden", timeout_per_test=task.get("test_timeout_s", 60), copy_in=True)
        return vis, hid


def main():
    ok = True
    for td in sorted(p for p in TASKS.iterdir() if (p / "task.json").exists()):
        task = json.loads((td / "task.json").read_text())
        print(f"== {task['id']}  ({task['difficulty']}, {task['kind']})")
        vis, hid = score(td, task)
        print(f"   {'starter':24s} visible {vis['passed']}/{vis['total']}  hidden {hid['passed']}/{hid['total']}")
        good = hid["passed"] < hid["total"]
        for sol in sorted(RUNS.glob(f"{td.name}__*/solution")):
            vis, hid = score(td, task, sol)
            this = vis["passed"] == vis["total"] > 0 and hid["passed"] == hid["total"] > 0
            print(f"   {sol.parent.name.split('__')[1]:24s} visible {vis['passed']}/{vis['total']}  hidden {hid['passed']}/{hid['total']}  {'ok' if this else 'FAIL'}")
            good &= this
        print("   ->", "OK" if good else "PROBLEM")
        ok &= good
    print("SELF-CHECK", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
