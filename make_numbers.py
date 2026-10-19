#!/usr/bin/env python3
"""Turn results/<session>/results.jsonl into script_numbers.json + summary.md for SCRIPT_v3.md.

  python make_numbers.py results/live-YYYYMMDD-HHMMSS
Keys match the ⟦RESULT key⟧ placeholders: <h>.<t>.<field> and <h>.total.<field>
  h: ds (OpenCode + DeepSeek), sonnet (Claude Code + Sonnet 5.5), gpt (Codex + GPT-6.1 Sol), ctl (Claude Code + DeepSeek, optional)
  t: t1, t2, t3
"""
import json
import pathlib
import sys

H = {"opencode-deepseek": "ds", "claude-sonnet": "sonnet", "codex-gpt": "gpt", "claude-deepseek": "ctl"}


def money(x):
    return f"{x * 100:.1f} cents" if x < 1 else f"${x:.2f}"


def main(session):
    session = pathlib.Path(session)
    rows = [json.loads(l) for l in (session / "results.jsonl").read_text().splitlines() if l.strip()]
    dry = any(r.get("mode") == "mock" for r in rows)
    nums, lines = {"_source": str(session / "results.jsonl"), "_dry_run": dry}, []
    totals = {}
    for r in rows:
        h, t = H.get(r["harness"], r["harness"]), r["task"][:2]
        if r.get("skipped"):
            nums[f"{h}.{t}.status"] = f"skipped ({r['skipped']})"
            continue
        tok = r["tokens"]
        if r["solved"]:
            status = "solved"
        elif r["finished"]:
            status = "finished, not solved"
        elif tok["in_total"] == 0 and r["exit_code"] not in (0, None):
            status = "blocked: OpenRouter returned 404 before any model work (0 tokens)"
        else:
            status = f"stopped: {r['stop_reason'] or r['ended']}"
        b = r.get("billed") or {}
        gen_found = b.get("found", 0)
        src = ("OpenRouter usage.cost per response" + (f"; generation stats found for {gen_found} of {r['model_requests']} requests" if r["model_requests"] else ""))
        fields = {
            "status": status, "solved": r["solved"], "finished": r["finished"],
            "hidden": f"{r['hidden_passed']}/{r['hidden_total']}", "visible": f"{r['visible_passed']}/{r['visible_total']}",
            "requests": r["model_requests"], "wall": f"{r['wall_s'] / 60:.1f} min",
            "in": tok["in_total"], "cached": tok["cache_read"], "cache_write": tok["cache_write"],
            "out": tok["out"], "reasoning": tok["reasoning"],
            "cost": r["proxy_spent_usd"], "cost_str": money(r["proxy_spent_usd"]), "cost_source": src,
            "providers": (r.get("billed") or {}).get("providers"), "edited_tests": r["edited_visible_tests"],
        }
        for k, v in fields.items():
            nums[f"{h}.{t}.{k}"] = v
        tt = totals.setdefault(h, {"cost": 0.0, "solved": 0, "runs": 0, "wall_s": 0.0, "out": 0, "in": 0})
        tt["cost"] += r["proxy_spent_usd"]
        tt["solved"] += int(r["solved"])
        tt["runs"] += 1
        tt["wall_s"] += r["wall_s"]
        tt["out"] += tok["out"]
        tt["in"] += tok["in_total"]
        lines.append(f"| {r['label']} | {r['task']} | {status} | {fields['hidden']} | {r['model_requests']} | {fields['wall']} | "
                     f"{tok['in_total']:,} ({tok['cache_read']:,}) | {tok['out']:,} | {money(r['proxy_spent_usd'])} | {src} |")
    for h, tt in totals.items():
        nums[f"{h}.total.cost"] = round(tt["cost"], 6)
        nums[f"{h}.total.cost_str"] = money(tt["cost"])
        nums[f"{h}.total.solved"] = f"{tt['solved']}/{tt['runs']}"
        nums[f"{h}.total.wall"] = f"{tt['wall_s'] / 60:.1f} min"
        nums[f"{h}.total.out"] = tt["out"]
        nums[f"{h}.total.cost_per_solved"] = money(tt["cost"] / tt["solved"]) if tt["solved"] else "n/a"
    nums["all.total.cost"] = round(sum(t["cost"] for t in totals.values()), 6)
    (session / "script_numbers.json").write_text(json.dumps(nums, indent=1))
    head = ("# DRY RUN (mock model, nothing billed); NOT results\n\n" if dry else "# SCO-637 harness-vs-harness results\n\n")
    md = head + "| Harness | Task | Status | Hidden tests | Model requests | Wall | Tokens in (cached) | Tokens out | Billed | Cost source |\n|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(lines)
    md += f"\n\nTotal billed: {money(nums['all.total.cost'])}\n"
    (session / "summary.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main(sys.argv[1])
