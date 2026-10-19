# Ticket: report is far too slow

`build_report` takes minutes on a day of logs (~200,000 lines). It must handle 200,000 lines in
well under 3 seconds on a normal laptop, and its output must stay **exactly** the same as today
for every input (same keys, same values, same ordering, same tie-breaking, same handling of
malformed lines). Treat the current behaviour as the spec, including its quirks.
