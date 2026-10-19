#!/usr/bin/env python3
"""SCO-637 harness-vs-harness runner (Claude Code / Codex CLI / OpenCode, all via OpenRouter).

  python runner.py --plan A --estimate            # cap math only, no processes, no network
  python runner.py --plan A --dry-run             # $0: mock proxy, real CLIs, real repos, scoring
  python runner.py --plan A --run --confirm       # PAID: needs OPENROUTER_API_KEY in the env

Key handling: the key is read from the environment of this process only, handed to each
harness through its environment at run time, never printed, never logged and never written to
any file (configs reference the env var by name). Logs are scrubbed for the key value anyway.
All harness state lives in throwaway folders under ./.sandbox/<session>/; ~/.claude, ~/.codex
and any subscription login are never read or touched.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

from scoring import run_pytest

ROOT = pathlib.Path(__file__).resolve().parent
TOOLS_BIN = ROOT / "tools" / "node_modules" / ".bin"
VENV_BIN = ROOT / ".venv-tests" / "bin"
RESULTS = ROOT / "results"
LEDGER = RESULTS / "spend_ledger.json"
DUMMY = "sk-or-v1-DRYRUN-NOT-A-REAL-KEY-0000000000000000"
KEY_ENV = "OPENROUTER_API_KEY"

CFG = json.loads((ROOT / "harnesses.json").read_text())
PRICES = json.loads((ROOT / "prices.json").read_text())["models"]
LIMITS = CFG["limits"]
CAP = LIMITS["global_cap_usd"]


def tasks():
    out = {}
    for p in sorted((ROOT / "tasks").iterdir()):
        if (p / "task.json").exists():
            out[p.name] = json.loads((p / "task.json").read_text())
    return out


TASKS = tasks()


def plan_runs(name):
    p = CFG["plans"][name]
    if "extends" in p:
        base = plan_runs(p["extends"])
        return base + [(t, h, b) for t, h, b in p["extra"]]
    return [(t, h, p["budget_usd"][t][h]) for t, h in p["order"]]


# ----------------------------------------------------------------------------- money

def guard_rates(model):
    pr = PRICES[model]["standard"]
    in_guard = max(pr["in"], pr.get("cache_write", pr["in"]), pr.get("cache_write_1h", 0))
    return pr, in_guard


def overshoot_allowance(model):
    """Max amount one run can exceed its budget: one cache miss on a max-size request."""
    pr, in_guard = guard_rates(model)
    return LIMITS["max_input_tokens_per_request"] * (in_guard - pr["cache_read"]) / 1e6


def worst_single_request(model):
    pr, in_guard = guard_rates(model)
    return (LIMITS["max_input_tokens_per_request"] * in_guard + LIMITS["max_output_tokens_per_request"] * pr["out"]) / 1e6


def ledger():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"cap_usd": CAP, "total_usd": 0.0, "runs": []}


def save_ledger(l):
    RESULTS.mkdir(exist_ok=True)
    tmp = LEDGER.with_suffix(".tmp")
    tmp.write_text(json.dumps(l, indent=1))
    os.replace(tmp, LEDGER)


def estimate_table(plan):
    rows, tot_budget, tot_over = [], 0.0, 0.0
    for t, h, b in plan_runs(plan):
        hz = CFG["harnesses"][h]
        ov = overshoot_allowance(hz["model"])
        rows.append((t, h, b, ov, TASKS[t]["max_requests"], TASKS[t]["wall_time_s"]))
        tot_budget += b
        tot_over += ov
    return rows, tot_budget, tot_over


def print_estimate(plan):
    rows, tb, to = estimate_table(plan)
    print(f"PLAN {plan}: {len(rows)} runs (n=1 per task x harness)   global hard cap ${CAP:.2f}")
    print(f"{'task':22s} {'harness':18s} {'budget':>7s} {'1-miss overshoot':>17s} {'req cap':>7s} {'wall':>6s}")
    for t, h, b, ov, n, w in rows:
        print(f"{t:22s} {h:18s} ${b:6.2f} {'$%.3f' % ov:>17s} {n:7d} {w//60:4d}m")
    print(f"sum of per-run budgets: ${tb:.2f}   (plus at most one cache-miss overshoot per run; the global guard below")
    print(f"never starts a run unless  spent_so_far + run_budget + that run's overshoot <= ${CAP:.2f},")
    print(f"shrinking the run budget to fit or skipping the run, so the total can never pass ${CAP:.2f}).")
    for m in sorted({CFG['harnesses'][h]['model'] for _, h, _ in plan_runs(plan)}):
        print(f"  worst single request {m}: ${worst_single_request(m):.3f}  (100k in at guard rate + {LIMITS['max_output_tokens_per_request']:,} out)")
    return tb


# ----------------------------------------------------------------------------- run setup

def scrub(text, key):
    return text.replace(key, "[REDACTED]") if key else text


def write_configs(run_dir, h, port):
    hz = CFG["harnesses"][h]
    model = hz["model"]
    d = {k: run_dir / k for k in ("home", "claude_cfg", "codex_home", "xdg_config", "xdg_data", "xdg_cache", "xdg_state", "tmp")}
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{port}"
    # login shells (Codex runs `bash -lc`) reset PATH from /etc/profile; give every harness the
    # same PATH back through the throwaway HOME so `python -m pytest` works identically for all
    prof = f'export PATH="{TOOLS_BIN}:{VENV_BIN}:$PATH"\n'
    for f in (".profile", ".bash_profile", ".bashrc"):
        (d["home"] / f).write_text(prof)
    if hz["cli"] == "codex":
        (d["codex_home"] / "config.toml").write_text(f'''# throwaway Codex config for one SCO-637 run (no key in this file)
model_provider = "openrouter"
model = "{model}"
model_reasoning_effort = "high"
web_search = "disabled"
check_for_update_on_startup = false

[features]
multi_agent = false
apps = false
enable_request_compression = false

[analytics]
enabled = false

[feedback]
enabled = false

[history]
persistence = "none"

[model_providers.openrouter]
name = "openrouter"
base_url = "{base}/api/v1"
wire_api = "responses"
request_max_retries = 1
stream_max_retries = 1

[model_providers.openrouter.auth]
command = "sh"
args = ["-c", "printf %s \\"${KEY_ENV}\\""]
''')
    if hz["cli"] == "opencode":
        oc = {
            "$schema": "https://opencode.ai/config.json",
            "model": f"openrouter/{model}",
            "small_model": f"openrouter/{model}",
            "autoupdate": False,
            "share": "disabled",
            "provider": {"openrouter": {
                "options": {"baseURL": f"{base}/api/v1", "apiKey": "{env:" + KEY_ENV + "}"},
                "models": {model: {"options": {"provider": {"only": [hz["pin"]], "order": [hz["pin"]], "allow_fallbacks": False}}}},
            }},
            "permission": {"edit": "allow", "bash": "allow", "webfetch": "deny", "websearch": "deny", "task": "deny",
                           "external_directory": "deny"},
        }
        (d["xdg_config"] / "opencode").mkdir(parents=True, exist_ok=True)
        (d["xdg_config"] / "opencode" / "opencode.json").write_text(json.dumps(oc, indent=2))
    return d


def harness_env(h, d, port, key):
    hz = CFG["harnesses"][h]
    model = hz["model"]
    env = {
        "PATH": f"{TOOLS_BIN}:{VENV_BIN}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(d["home"]), "TMPDIR": str(d["tmp"]), "LANG": "C.UTF-8", "TERM": "dumb", "NO_COLOR": "1",
        "XDG_CONFIG_HOME": str(d["xdg_config"]), "XDG_DATA_HOME": str(d["xdg_data"]),
        "XDG_CACHE_HOME": str(d["xdg_cache"]), "XDG_STATE_HOME": str(d["xdg_state"]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    base = f"http://127.0.0.1:{port}"
    if hz["cli"] == "claude":
        env.update({
            "CLAUDE_CONFIG_DIR": str(d["claude_cfg"]),
            "ANTHROPIC_BASE_URL": f"{base}/api",
            "ANTHROPIC_AUTH_TOKEN": key,
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_MODEL": model,
            "ANTHROPIC_DEFAULT_FABLE_MODEL": model, "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": model, "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
            "ANTHROPIC_SMALL_FAST_MODEL": model, "CLAUDE_CODE_SUBAGENT_MODEL": model,
            "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "DISABLE_BUG_COMMAND": "1",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(LIMITS["max_output_tokens_per_request"]),
        })
    elif hz["cli"] == "codex":
        env.update({"CODEX_HOME": str(d["codex_home"]), KEY_ENV: key})
    elif hz["cli"] == "opencode":
        env.update({KEY_ENV: key, "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1",
                    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1"})
    return env


def harness_cmd(h, task, ws):
    hz = CFG["harnesses"][h]
    prompt = task["prompt"]
    if hz["cli"] == "claude":
        return ["claude", "-p", prompt, "--model", hz["model"], "--output-format", "stream-json", "--verbose",
                "--dangerously-skip-permissions", "--no-session-persistence", "--strict-mcp-config",
                "--setting-sources", "", "--tools", "Bash,Read,Edit,Write,Glob,Grep,TodoWrite"]
    if hz["cli"] == "codex":
        return ["codex", "exec", "--json", "--skip-git-repo-check", "--ephemeral", "--sandbox", "workspace-write",
                "-C", str(ws), prompt]
    if hz["cli"] == "opencode":
        return ["opencode", "run", "--format", "json", "--auto", "--pure", "--title", f"sco637-{task['id']}", "--variant", "high",
                "-m", f"openrouter/{hz['model']}", "--dir", str(ws), prompt]
    raise ValueError(h)


def git(ws, *args):
    return subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@local", *args], cwd=ws,
                          capture_output=True, text=True)


def start_proxy(run_dir, h, task, mode, budget):
    hz = CFG["harnesses"][h]
    pr, in_guard = guard_rates(hz["model"])
    pdir = run_dir / "proxy"
    pdir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "run_id": run_dir.name, "mode": mode, "listen_port": 0, "upstream_host": "openrouter.ai",
        "model": hz["model"], "pin": hz["pin"], "max_requests": task["max_requests"], "budget_usd": budget,
        "max_output_tokens": LIMITS["max_output_tokens_per_request"],
        "max_input_tokens": LIMITS["max_input_tokens_per_request"],
        "prices": pr, "input_guard_rate": in_guard, "cache_write_guard_rate": in_guard,
        "log": str(pdir / "requests.jsonl"), "state": str(pdir / "state.json"),
        "stop_flag": str(pdir / "STOP"), "port_file": str(pdir / "port"),
    }
    if mode == "mock":
        cfg["dump_bodies_dir"] = str(pdir / "mock_bodies")  # dry run only: request bodies, for the fairness notes
    (pdir / "config.json").write_text(json.dumps(cfg, indent=1))
    penv = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    if mode == "mock":
        penv["SCO637_DRYRUN_DUMMY"] = DUMMY
    proc = subprocess.Popen([sys.executable, str(ROOT / "proxy.py"), "--config", str(pdir / "config.json")],
                            env=penv, stdout=open(pdir / "proxy.out", "w"), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(100):
        if (pdir / "port").exists() and (pdir / "port").read_text().strip():
            return proc, int((pdir / "port").read_text()), pdir
        time.sleep(0.05)
    proc.kill()
    raise RuntimeError("proxy did not start")


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001
            pass


def reconcile(gen_ids, key, max_seconds=180):
    """Billed cost from OpenRouter generation stats (live runs only). Bounded in time: if stats are not
    found, the caller falls back to OpenRouter's per-response usage.cost recorded by the proxy."""
    out = {"billed_usd": 0.0, "found": 0, "missing": [], "providers": {}, "native": {"prompt": 0, "completion": 0, "cached": 0, "reasoning": 0}}
    t_end = time.time() + max_seconds
    attempts = 8
    for gid in dict.fromkeys(gen_ids):
        data = None
        for attempt in range(attempts):
            if time.time() > t_end:
                break
            req = urllib.request.Request(f"https://openrouter.ai/api/v1/generation?id={gid}",
                                         headers={"Authorization": f"Bearer {key}"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read()).get("data")
                    break
            except Exception:  # noqa: BLE001  (404 while stats are still being written)
                time.sleep(min(2 + attempt, 6))
        if not data:
            out["missing"].append(gid)
            attempts = 2  # ids of this kind may not be generation ids; don't stall the run
            continue
        attempts = 4
        out["found"] += 1
        out["billed_usd"] += float(data.get("total_cost") or 0)
        pn = data.get("provider_name") or "?"
        out["providers"][pn] = out["providers"].get(pn, 0) + 1
        for k_out, k_in in (("prompt", "native_tokens_prompt"), ("completion", "native_tokens_completion"),
                            ("cached", "native_tokens_cached"), ("reasoning", "native_tokens_reasoning")):
            out["native"][k_out] += int(data.get(k_in) or 0)
    return out


def summarize_proxy(pdir):
    recs = [json.loads(l) for l in (pdir / "requests.jsonl").read_text().splitlines()] if (pdir / "requests.jsonl").exists() else []
    state = json.loads((pdir / "state.json").read_text()) if (pdir / "state.json").exists() else {}
    model_reqs = [r for r in recs if r.get("decision") in ("forwarded", "mock")]
    tok = {"in_total": 0, "cache_read": 0, "cache_write": 0, "out": 0, "reasoning": 0}
    for r in model_reqs:
        for k in tok:
            tok[k] += int(((r.get("usage") or {}).get(k)) or 0)
    first = model_reqs[0] if model_reqs else {}
    return {
        "model_requests": len(model_reqs), "refused": [r.get("reason") for r in recs if r.get("decision") == "refused"],
        "proxy_spent_usd": state.get("spent_usd", 0.0), "stop_reason": state.get("stop_reason"),
        "gen_ids": state.get("gen_ids", []), "tokens": tok,
        "first_request": {k: first.get(k) for k in ("path", "api", "model", "stream", "tools_count", "tool_names",
                                                    "tools_bytes", "system_chars", "est_in_tokens", "provider_pin",
                                                    "max_out_requested", "auth_header", "auth_is_dryrun_dummy",
                                                    "stripped_service_tier", "harness_sent_provider", "max_out_clamped")},
        "mock_replies": [r.get("mock_reply") for r in model_reqs if r.get("mock_reply")],
        "tool_result_seen": next((r.get("tool_result_seen") for r in model_reqs if r.get("tool_result_seen")), None),
        "other_paths": sorted({r.get("path") for r in recs if r.get("decision") not in ("forwarded", "mock")}),
    }


def one_run(session_dir, t, h, budget, mode, key):
    task = TASKS[t]
    run_dir = session_dir / f"{t}__{h}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    ws = run_dir / "ws"
    shutil.copytree(ROOT / "tasks" / t / "repo", ws)
    git(ws, "init", "-q")
    git(ws, "add", "-A")
    git(ws, "commit", "-qm", "starter")
    proxy, port, pdir = start_proxy(run_dir, h, task, mode, budget)
    d = write_configs(run_dir, h, port)
    env = harness_env(h, d, port, key)
    cmd = harness_cmd(h, task, ws)
    wall = task["wall_time_s"] if mode == "live" else 180
    t0 = time.time()
    out_f = open(run_dir / "harness.stdout.jsonl", "w")
    err_f = open(run_dir / "harness.stderr.txt", "w")
    proc = subprocess.Popen(cmd, cwd=ws, env=env, stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL,
                            start_new_session=True)
    ended = "exited"
    while proc.poll() is None:
        if time.time() - t0 > wall:
            ended = "wall_time"
            kill_group(proc)
            break
        if (pdir / "STOP").exists():
            time.sleep(3)  # let the harness print its own error, then stop it
            if proc.poll() is None:
                ended = "proxy_stop:" + (pdir / "STOP").read_text().strip()
                kill_group(proc)
            break
        time.sleep(0.5)
    secs = time.time() - t0
    rc = proc.returncode
    out_f.close()
    err_f.close()
    time.sleep(0.5)
    kill_group(proxy)
    for f in (run_dir / "harness.stdout.jsonl", run_dir / "harness.stderr.txt"):
        f.write_text(scrub(f.read_text(errors="replace"), key))
    px = summarize_proxy(pdir)
    # score: copy the agent's final tree, then copy hidden tests in (the agent never saw them)
    diff = git(ws, "diff", "--numstat", "HEAD").stdout + git(ws, "status", "--porcelain").stdout
    edited_tests = any(line.split("\t")[-1].startswith("tests/") for line in git(ws, "diff", "--numstat", "HEAD").stdout.splitlines())
    score_ws = run_dir / "score_ws"
    shutil.copytree(ws, score_ws, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    shutil.rmtree(score_ws / "tests", ignore_errors=True)
    shutil.copytree(ROOT / "tasks" / t / "repo" / "tests", score_ws / "tests")  # pristine visible tests
    vis = run_pytest(score_ws, score_ws / "tests", timeout_per_test=task["test_timeout_s"])
    hid = run_pytest(score_ws, ROOT / "tasks" / t / "hidden", timeout_per_test=task["test_timeout_s"], copy_in=True)
    rec = {
        "time": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "mode": mode, "task": t, "harness": h,
        "label": CFG["harnesses"][h]["label"], "model": CFG["harnesses"][h]["model"], "budget_usd": budget,
        "wall_s": round(secs, 1), "exit_code": rc, "ended": ended,
        "finished": ended == "exited" and rc == 0 and not px["stop_reason"],
        "hidden_passed": hid["passed"], "hidden_total": hid["total"],
        "visible_passed": vis["passed"], "visible_total": vis["total"],
        "solved": hid["total"] > 0 and hid["passed"] == hid["total"] and vis["passed"] == vis["total"],
        "edited_visible_tests": edited_tests, "changed_files": len([l for l in diff.splitlines() if l.strip()]),
        **{k: px[k] for k in ("model_requests", "refused", "proxy_spent_usd", "stop_reason", "tokens", "first_request",
                              "mock_replies", "tool_result_seen", "other_paths")},
    }
    if mode == "live":
        rc_ = reconcile(px["gen_ids"], key)
        rec["billed"] = rc_
        rec["billed_usd"] = rc_["billed_usd"] if not rc_["missing"] else max(rc_["billed_usd"], px["proxy_spent_usd"])
        rec["billed_source"] = "openrouter_generation_stats" if not rc_["missing"] else "partial_stats_or_proxy_usage"
    else:
        rec["billed_usd"] = 0.0
        rec["billed_source"] = "dry run: nothing sent to any model"
    (run_dir / "result.json").write_text(json.dumps(rec, indent=1))
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=CFG.get("default_plan", "B"), choices=sorted(CFG["plans"]))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--estimate", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--only", help="comma list of task__harness to run (subset of the plan)")
    args = ap.parse_args()

    total_budget = print_estimate(args.plan)
    if args.estimate:
        return 0
    if total_budget > CAP:
        print(f"ABORT: plan budgets ${total_budget:.2f} exceed the ${CAP:.2f} cap")
        return 2
    runs = plan_runs(args.plan)
    if args.only:
        keep = set(args.only.split(","))
        runs = [r for r in runs if f"{r[0]}__{r[1]}" in keep]

    if args.dry_run:
        mode, key = "mock", DUMMY
    else:
        if not args.confirm:
            print("Refusing: a paid run needs --run --confirm.")
            return 2
        key = os.environ.get(KEY_ENV, "")
        if not key:
            print(f"Refusing: {KEY_ENV} is not set.")
            return 2
        mode = "live"

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    session = ROOT / ".sandbox" / f"{'dryrun' if mode == 'mock' else 'live'}-{stamp}"
    session.mkdir(parents=True)
    out_dir = RESULTS / session.name
    out_dir.mkdir(parents=True)
    led = ledger() if mode == "live" else {"cap_usd": CAP, "total_usd": 0.0, "runs": []}
    results = []
    for t, h, budget in runs:
        allowance = overshoot_allowance(CFG["harnesses"][h]["model"])
        remaining = CAP - led["total_usd"]
        eff = round(min(budget, remaining - allowance), 4)
        if eff < 0.5 * budget:
            print(f"SKIP {t} / {h}: global cap. spent ${led['total_usd']:.3f}, need ${budget:.2f} + ${allowance:.3f} reserve")
            results.append({"task": t, "harness": h, "skipped": "global_cap"})
            continue
        print(f"-> {t} / {h}  budget ${eff:.2f}{' (shrunk)' if eff < budget else ''}  mode={mode}", flush=True)
        rec = one_run(session, t, h, eff, mode, key)
        results.append(rec)
        if mode == "live":
            led["total_usd"] += rec["billed_usd"]
            led["runs"].append({k: rec[k] for k in ("time", "task", "harness", "billed_usd", "billed_source")})
            save_ledger(led)
        print(f"   ended={rec['ended']} exit={rec['exit_code']} reqs={rec['model_requests']} hidden {rec['hidden_passed']}/{rec['hidden_total']}"
              f" visible {rec['visible_passed']}/{rec['visible_total']} wall {rec['wall_s']}s billed ${rec['billed_usd']:.4f}"
              f"  running total ${led['total_usd']:.4f}", flush=True)
    with open(out_dir / "results.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"results: {out_dir/'results.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
