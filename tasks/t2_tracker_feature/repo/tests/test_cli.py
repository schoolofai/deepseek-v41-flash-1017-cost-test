import json
from tracker.cli import main


def run(db, *argv):
    return main(["--db", str(db), *argv])


def test_add_list_done(tmp_path, capsys):
    db = tmp_path / "t.json"
    assert run(db, "add", "Write report") == 0
    assert run(db, "add", "Call Bob") == 0
    assert run(db, "done", "1") == 0
    capsys.readouterr()
    run(db, "list")
    assert capsys.readouterr().out.splitlines() == ["[x] 1 Write report", "[ ] 2 Call Bob"]


def test_empty(tmp_path, capsys):
    run(tmp_path / "t.json", "list")
    assert capsys.readouterr().out.strip() == "no tasks"


def test_done_missing(tmp_path, capsys):
    assert run(tmp_path / "t.json", "done", "9") == 1


def test_due_and_tags_render(tmp_path, capsys):
    db = tmp_path / "t.json"
    run(db, "add", "Ship", "--due", "2026-10-25", "--tag", "work", "--tag", "Urgent")
    capsys.readouterr()
    run(db, "list")
    assert capsys.readouterr().out.strip() == "[ ] 1 Ship (due 2026-10-25) #work #urgent"
