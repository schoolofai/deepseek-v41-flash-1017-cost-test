import json
import subprocess
import sys

import pytest
from tracker.cli import main


def run(db, *argv):
    return main(["--db", str(db), *argv])


def ids(lines):
    return [l[4:].split()[0] for l in lines]


def listed(db, capsys, *argv):
    capsys.readouterr()
    rc = run(db, "list", *argv)
    assert rc == 0
    return capsys.readouterr().out.splitlines()


@pytest.fixture
def db(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("TRACKER_TODAY", raising=False)
    p = tmp_path / "t.json"
    run(p, "add", "Old plain")                                                  # 1
    run(p, "add", "Ship", "--due", "2026-10-25", "--tag", "work", "--tag", "Urgent")  # 2
    run(p, "add", "Tax", "--due", "2026-10-01", "--tag", "home")                # 3
    run(p, "add", "Gym", "--tag", "home", "--tag", "HOME", "--tag", "health")   # 4
    run(p, "add", "Invoice", "--due", "2026-10-10", "--tag", "work")            # 5
    run(p, "done", "5")
    capsys.readouterr()
    return p


def test_render_all(db, capsys):
    assert listed(db, capsys) == [
        "[ ] 1 Old plain",
        "[ ] 2 Ship (due 2026-10-25) #work #urgent",
        "[ ] 3 Tax (due 2026-10-01) #home",
        "[ ] 4 Gym #home #health",
        "[x] 5 Invoice (due 2026-10-10) #work",
    ]


def test_tag_filter_case_insensitive_and_all(db, capsys):
    assert ids(listed(db, capsys, "--tag", "WORK")) == ["2", "5"]
    assert ids(listed(db, capsys, "--tag", "work", "--tag", "urgent")) == ["2"]
    assert listed(db, capsys, "--tag", "nope") == ["no tasks"]


def test_overdue_today_flag(db, capsys):
    out = listed(db, capsys, "--overdue", "--today", "2026-10-19")
    assert out == ["[ ] 3 Tax (due 2026-10-01) #home"]   # 5 is done, 2 not yet due


def test_overdue_strictly_before(db, capsys):
    assert listed(db, capsys, "--overdue", "--today", "2026-10-01") == ["no tasks"]


def test_overdue_env(db, capsys, monkeypatch):
    monkeypatch.setenv("TRACKER_TODAY", "2026-10-26")
    out = listed(db, capsys, "--overdue")
    assert ids(out) == ["2", "3"]


def test_sort_due(db, capsys):
    out = listed(db, capsys, "--sort", "due")
    assert ids(out) == ["3", "5", "2", "1", "4"]
    assert ids(listed(db, capsys, "--sort", "id")) == ["1", "2", "3", "4", "5"]


def test_combined_filters(db, capsys):
    out = listed(db, capsys, "--tag", "home", "--sort", "due", "--overdue", "--today", "2026-12-01")
    assert out == ["[ ] 3 Tax (due 2026-10-01) #home"]


@pytest.mark.parametrize("bad", ["2026-02-30", "2026-13-01", "26-10-01", "tomorrow", "2026-1-5"])
def test_invalid_due(tmp_path, capsys, bad):
    p = tmp_path / "t.json"
    rc = run(p, "add", "X", "--due", bad)
    err = capsys.readouterr().err
    assert rc == 2
    assert f"error: invalid date: {bad}" in err
    assert not p.exists()


def test_saved_format_v2(db):
    data = json.loads(db.read_text())
    assert data["version"] == 2
    t4 = [t for t in data["tasks"] if t["id"] == 4][0]
    assert t4["due"] is None and t4["tags"] == ["home", "health"]
    t2 = [t for t in data["tasks"] if t["id"] == 2][0]
    assert t2["due"] == "2026-10-25" and t2["tags"] == ["work", "urgent"]


def test_v1_file_loads_and_upgrades(tmp_path, capsys):
    p = tmp_path / "old.json"
    p.write_text(json.dumps({"next_id": 3, "tasks": [
        {"id": 1, "title": "Legacy", "done": True}, {"id": 2, "title": "Legacy two", "done": False}]}))
    assert listed(p, capsys) == ["[x] 1 Legacy", "[ ] 2 Legacy two"]
    assert listed(p, capsys, "--sort", "due") == ["[x] 1 Legacy", "[ ] 2 Legacy two"]
    run(p, "add", "New", "--tag", "x")
    data = json.loads(p.read_text())
    assert data["version"] == 2 and data["next_id"] == 4
    assert data["tasks"][0]["tags"] == [] and data["tasks"][0]["due"] is None


def test_module_entrypoint(tmp_path):
    p = tmp_path / "t.json"
    r = subprocess.run([sys.executable, "-m", "tracker", "--db", str(p), "add", "Y", "--due", "2026-11-31"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "invalid date" in r.stderr
