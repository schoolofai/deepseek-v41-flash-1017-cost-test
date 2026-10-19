# logstats
Builds a usage report from access-log lines like

    2026-10-19T10:00:00Z user=alice path=/api/items status=200 ms=123

`build_report(lines)` in `logstats/report.py` is the entry point. Run tests with `python -m pytest -q`.
