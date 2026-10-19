import argparse
import sys

from .storage import Store


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tracker")
    p.add_argument("--db", default="tasks.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("title")
    sub.add_parser("list")
    d = sub.add_parser("done")
    d.add_argument("id", type=int)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(args.db)
    if args.cmd == "add":
        t = store.add(args.title)
        store.save()
        print(f"added {t.id}")
        return 0
    if args.cmd == "list":
        if not store.tasks:
            print("no tasks")
        for t in store.tasks:
            print(t.render())
        return 0
    if args.cmd == "done":
        try:
            store.get(args.id).done = True
        except KeyError:
            print(f"error: no task {args.id}", file=sys.stderr)
            return 1
        store.save()
        print(f"done {args.id}")
        return 0
    return 1
