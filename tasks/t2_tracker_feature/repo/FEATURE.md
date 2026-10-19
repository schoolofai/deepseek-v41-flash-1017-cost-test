# Feature request: due dates and tags

Product wants due dates and tags. Implement all of this; keep every existing behaviour working.

## add
- `add TITLE [--due YYYY-MM-DD] [--tag NAME ...]` — `--tag` may be repeated. Tags are stored
  lower-cased, de-duplicated, in the order first given.
- An invalid `--due` (not a real calendar date in `YYYY-MM-DD` form) prints
  `error: invalid date: <value>` to **stderr**, does not save anything and exits with status **2**.

## list
- Output format for each task (one line):
  `[x] 3 Title (due 2026-10-25) #work #urgent`
  — `[ ]` for open tasks, `[x]` for done; the ` (due …)` part only when there is a due date;
  then ` #tag` for each tag in stored order. Tasks without due date or tags print exactly as today.
- `--tag NAME` (case-insensitive) shows only tasks having that tag. May be repeated: a task must
  have **all** the given tags.
- `--overdue` shows only open (not done) tasks whose due date is strictly before *today*.
- *Today* is `--today YYYY-MM-DD` if given on `list`, else the env var `TRACKER_TODAY`, else the
  real local date.
- `--sort due` orders by due date ascending, tasks without a due date last; ties by id.
  Default order (no `--sort`) stays by id. `--sort id` is also accepted.
- Filters combine (AND). When nothing matches, print `no tasks`.

## storage
- New files are saved as `{"version": 2, "next_id": N, "tasks": [...]}` where each task has
  `id`, `title`, `done`, `due` (string or null) and `tags` (list).
- Old files (version 1: no `version` key, tasks without `due`/`tags`) must still load; they are
  written back as version 2 on the next save.
