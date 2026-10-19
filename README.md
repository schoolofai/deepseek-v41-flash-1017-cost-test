# deepseek-v41-flash-1017-cost-test

**Video:** VIDEO_URL_TBD (ProAI Clips, "DeepSeek V4.1 Flash 1017: Same Coding Tasks, 2¢ vs 20¢ vs 39¢ (Real Receipts)")

Three AI coding agents get the same two small, real repo tasks. Hidden tests decide pass or fail, and OpenRouter's own billing records give the receipt.

| Agent (harness) | Model (OpenRouter id) | Pinned provider |
|---|---|---|
| OpenCode 1.19.3 | `deepseek/deepseek-v4.1-flash-1017` | DeepSeek |
| Claude Code 2.1.303 | `anthropic/claude-sonnet-5.5` | Anthropic |
| Codex CLI 0.163.0 | `openai/gpt-6.1-sol` | OpenAI |

## The filmed result (Mon 19 Oct 2026, one run each, API per-token prices)

| Both tasks | DeepSeek V4.1 Flash 1017 (OpenCode) | Sonnet 5.5 (Claude Code) | GPT-6.1 Sol (Codex) |
|---|---|---|---|
| Solved | 2/2 | 2/2 | 2/2 |
| Total billed | **2.0¢** ($0.0203) | 20.5¢ ($0.2048) | 39.3¢ ($0.3933) |
| Cost per solved task | 1.0¢ | 10.2¢ | 19.7¢ |
| Total time | 4.5 min | 1.4 min | 9.2 min |

| Task | Agent | Hidden tests | Requests | Time | Tokens in (cached) | Tokens out | Billed |
|---|---|---|---|---|---|---|---|
| t1 checkout bugs | DeepSeek / OpenCode | 30/30 | 6 | 28 s | 57,219 (47,744) | 3,837 | 0.4¢ |
| t1 checkout bugs | Sonnet / Claude Code | 30/30 | 5 | 22.5 s | 101,828 (79,423) | 2,825 | 9.2¢ |
| t1 checkout bugs | GPT / Codex | 30/30 | 8 | 1.8 min | 89,446 (71,817) | 5,491 | 10.6¢ |
| t3 log report speed-up | DeepSeek / OpenCode | 8/8 | 19 | 4.0 min | 425,525 (408,192) | 21,037 | 1.6¢ |
| t3 log report speed-up | Sonnet / Claude Code | 8/8 | 4 | 61 s | 81,985 (64,092) | 6,149 | 11.3¢ |
| t3 log report speed-up | GPT / Codex | 8/8 | 15 | 7.3 min | 306,651 (271,602) | 17,233 | 28.7¢ |

**Fairness note.** These are API per-token prices, not a Claude Code or Codex subscription (a flat fee works out differently). It's one run per agent on two small tasks, so luck plays a part. Each harness has its own system prompt and tools, so a result is "model + agent", not the model alone. DeepSeek ran in its off-peak window (half price); at its standard price the same run works out at about 4.1¢ (calculated, not a second run).

**Caveats from the run.**
- The first DeepSeek attempt was refused by OpenRouter (HTTP 404, 0 tokens, $0): "Paid model training violation (account settings)". The account's privacy setting excluded DeepSeek's own endpoint. After the setting was changed, only the two DeepSeek jobs were re-run. Logs for both attempts are in `results/`.
- Codex added and edited tests of its own (t1: `tests/test_spec.py`; t3: `tests/test_report.py` plus two new files). Scoring always puts the original visible tests back before grading, so its score is unaffected.
- Total spend for the whole test, including the blocked attempt: $0.6184 of a $3.00 cap.

Everything from the filmed runs is in [`results/filmed-2026-10-19/`](results/filmed-2026-10-19/): the summary table, every run's `result.json`, the proxy's per-request log (tokens, cost, provider), the agent's own event log, and **each agent's solution** (`solution/` plus `solution.diff`). Logs were scrubbed of machine paths and usernames; a few Codex commands that listed the test machine outside the task folder have their output redacted.

## What's in here

| Path | What it does |
|---|---|
| `tasks/t1_checkout_bugfix/` | Checkout library with bugs across 4 files (`repo/` = starter + visible tests, `hidden/` = 30 hidden tests) |
| `tasks/t3_logstats_perf/` | Slow log report: make it fast with byte-identical output, quirks included (8 hidden tests, incl. a 200k-line speed test) |
| `tasks/t2_tracker_feature/` | A third task (feature work, 15 hidden tests). **Not run in the video** (kept out to stay under the $3 cap). |
| `runner.py` | Runs each agent in a throwaway HOME/config folder, starts the proxy, scores with hidden tests, keeps the $3 ledger |
| `proxy.py` | Local metering proxy in front of OpenRouter: provider pin (no fallbacks), model allow-list, output clamp, request cap, per-run budget guard |
| `harnesses.json` | Agents, models, pins, plans (B = filmed), per-run budgets and limits |
| `prices.json` | Per-token prices used only for the pre-request budget guard (billing truth = OpenRouter) |
| `scoring.py`, `selfcheck.py`, `proxy_selftest.py` | Hidden-test scoring, a $0 task check, and an offline proxy test |
| `make_numbers.py` | Turns a run's `results.jsonl` into `summary.md` + `script_numbers.json` |
| `tools/` | Pinned versions of the three CLIs (`npm ci`) |

The private reference solutions are not published. `selfcheck.py` uses the filmed agents' solutions instead to prove the hidden tests can be passed.

## Quick start

Linux or macOS, Python 3.11+, Node 20+. Steps 1–5 cost nothing and need no key. Video timestamps are approximate until the final cut.

### 1. Clone (video 4:39)
What it is: the tasks, the hidden tests and the rig from the video.
```bash
git clone https://github.com/schoolofai/deepseek-v41-flash-1017-cost-test && cd deepseek-v41-flash-1017-cost-test
```
Expected: `tasks/  runner.py  proxy.py  harnesses.json  prices.json  results/ …`

### 2. Install the three agents and the test runner (video 4:51)
What it is: `tools/package-lock.json` pins Claude Code 2.1.303, Codex CLI 0.163.0 and OpenCode 1.19.3 locally (nothing global); pytest runs the hidden tests.
```bash
(cd tools && npm ci) && python3 -m venv .venv-tests && .venv-tests/bin/pip install pytest==8.4.2 pytest-timeout
ls tools/node_modules/.bin
```
Expected: `claude  codex  opencode` among the binaries.

### 3. Check the tasks ($0) (video 5:10)
What it is: `selfcheck.py` runs the hidden tests on each starter repo (must not pass) and on each filmed agent's solution (must pass).
```bash
python3 selfcheck.py
```
Expected (real output):
```
== t1_checkout_bugfix  (1 - easier, bugfix)
   starter                  visible 3/5  hidden 13/30
   claude-sonnet            visible 5/5  hidden 30/30  ok
   codex-gpt                visible 5/5  hidden 30/30  ok
   opencode-deepseek        visible 5/5  hidden 30/30  ok
   -> OK
...
SELF-CHECK PASSED
```

### 4. Test the safety rails ($0, offline) (video 6:16)
What it is: `proxy_selftest.py` drives `proxy.py` against a mock upstream: wrong model refused, provider pin injected, output clamp, budget guard, request cap.
```bash
python3 proxy_selftest.py && python3 runner.py --estimate
```
Expected: `PROXY SELF-TEST PASSED`, then the plan B table ending in `sum of per-run budgets: $2.77` under a `$3.00` hard cap.

### 5. Dry run the real agents with a mock model ($0, no key) (video 5:29)
What it is: every CLI really starts, talks to the local proxy with a dummy key, and a mock model answers. Nothing reaches a paid API.
```bash
python3 runner.py --dry-run
```
Expected: for each run, a line like `ended=exited exit=0 reqs=2 hidden 13/30 visible 3/5 wall 4.0s billed $0.0000`.

### 6. The paid run (real money, under $3) (video 6:23)
What it is: plan B, both tasks × three agents through OpenRouter, the key read only from the environment and never written to disk. Check your OpenRouter privacy settings first: if your account excludes providers that may train on paid prompts, DeepSeek's own endpoint is refused with a 404 (see Caveats).
```bash
export OPENROUTER_API_KEY=...        # never commit it; nothing in this repo stores it
python3 runner.py --run --confirm
```
Expected: one block per run, e.g. `ended=exited exit=0 reqs=6 hidden 30/30 visible 5/5 wall 28.0s billed $0.0039  running total $0.0039`, then `results: results/live-<stamp>/results.jsonl`. Re-run a subset with `--only t1_checkout_bugfix__opencode-deepseek,...`; the ledger in `results/spend_ledger.json` keeps the $3 cap across sessions.

### 7. Make the receipt table (video 6:48)
What it is: `make_numbers.py` sums OpenRouter's per-response cost and cross-checks generation records.
```bash
python3 make_numbers.py results/live-<stamp>
```
Expected: `results/live-<stamp>/summary.md` with one row per run (status, hidden tests, requests, wall time, tokens, billed, cost source), like `results/filmed-2026-10-19/summary.md`.

## Sources
- DeepSeek release note: https://api-docs.deepseek.com/news/news261017
- Model card: https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017
- DeepSeek pricing: https://api-docs.deepseek.com/quick_start/pricing
- OpenRouter model page: https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017
- OpenRouter provider routing: https://openrouter.ai/docs/guides/routing/provider-selection
- OpenRouter + Claude Code: https://openrouter.ai/docs/guides/coding-agents/claude-code
- OpenRouter + Codex CLI: https://openrouter.ai/docs/guides/coding-agents/codex-cli
- OpenCode providers: https://opencode.ai/docs/providers/

MIT licence. Made for ProAI Clips.
