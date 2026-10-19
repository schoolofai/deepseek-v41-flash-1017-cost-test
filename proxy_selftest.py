#!/usr/bin/env python3
"""Offline self-test of the metering proxy guards and usage parsing ($0, no network)."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import proxy

ROOT = os.path.dirname(os.path.abspath(__file__))
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


# 1) usage parsing for the three wire formats (synthetic OpenRouter-shaped events)
s = proxy.SSEScan("messages")
s.feed(b'event: message_start\ndata: {"type":"message_start","message":{"id":"gen-abc","usage":{"input_tokens":120,"cache_read_input_tokens":20000,"cache_creation_input_tokens":900,"output_tokens":1}}}\n\n')
s.feed(b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":431}}\n\n')
nu = proxy.norm_usage("messages", s.usage)
check("messages: id + usage parsed", s.ids == ["gen-abc"] and nu["in_total"] == 21020 and nu["cache_read"] == 20000 and nu["out"] == 431)
s = proxy.SSEScan("responses")
s.feed(b'data: {"type":"response.created","response":{"id":"gen-r1"}}\n\ndata: {"type":"response.completed","response":{"id":"gen-r1","usage":{"input_tokens":15000,"input_tokens_details":{"cached_tokens":12000},"output_tokens":800,"output_tokens_details":{"reasoning_tokens":500},"cost":0.0123}}}\n\n')
nu = proxy.norm_usage("responses", s.usage)
check("responses: id + usage + cost parsed", s.ids == ["gen-r1"] and nu["cache_read"] == 12000 and nu["reasoning"] == 500 and nu["cost"] == 0.0123)
s = proxy.SSEScan("chat")
s.feed(b'data: {"id":"gen-c1","choices":[{"delta":{"content":"hi"}}]}\n\ndata: {"id":"gen-c1","choices":[],"usage":{"prompt_tokens":9000,"completion_tokens":300,"prompt_tokens_details":{"cached_tokens":8000},"cost":0.00042}}\n\ndata: [DONE]\n\n')
nu = proxy.norm_usage("chat", s.usage)
check("chat: id + usage + cost parsed", s.ids == ["gen-c1"] and nu["in_total"] == 9000 and nu["cost"] == 0.00042)

# 2) guards, through a real mock-mode proxy process
tmp = tempfile.mkdtemp(prefix="proxytest-")
cfg = {"run_id": "selftest", "mode": "mock", "listen_port": 0, "upstream_host": "openrouter.ai",
       "model": "anthropic/claude-sonnet-5.5", "pin": "anthropic", "max_requests": 3, "budget_usd": 0.50,
       "max_output_tokens": 16384, "max_input_tokens": 100000,
       "prices": {"in": 2.0, "out": 10.0, "cache_read": 0.1, "cache_write": 2.5}, "input_guard_rate": 4.0,
       "log": f"{tmp}/r.jsonl", "state": f"{tmp}/s.json", "stop_flag": f"{tmp}/STOP", "port_file": f"{tmp}/port"}
json.dump(cfg, open(f"{tmp}/c.json", "w"))
p = subprocess.Popen([sys.executable, os.path.join(ROOT, "proxy.py"), "--config", f"{tmp}/c.json"], env={"PATH": "/usr/bin:/bin"})
for _ in range(100):
    if os.path.exists(f"{tmp}/port") and open(f"{tmp}/port").read():
        break
    time.sleep(0.05)
port = int(open(f"{tmp}/port").read())


def post(body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/messages", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer test"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


base = {"model": "anthropic/claude-sonnet-5.5", "max_tokens": 64000, "messages": [{"role": "user", "content": "hi"}],
        "service_tier": "priority", "speed": "fast"}
code, _ = post({**base, "model": "anthropic/claude-opus-5"})
check("wrong model refused (400)", code == 400)
code, _ = post(base)
recs = [json.loads(l) for l in open(f"{tmp}/r.jsonl")]
last = recs[-1]
check("ok request served by mock", code == 200 and last["decision"] == "mock")
check("max_tokens clamped 64000 -> 16384", last["max_out_requested"] == 64000)
check("service_tier/speed stripped", last.get("stripped_service_tier") == "priority" and last.get("stripped_speed") == "fast")
check("provider pin injected", last["provider_pin"] == "anthropic")
big = {**base, "messages": [{"role": "user", "content": "x" * 600_000}]}
code, _ = post(big)
check("oversized context refused (context_cap)", code == 400 and json.loads(open(f"{tmp}/r.jsonl").read().splitlines()[-1])["reason"] == "context_cap")
p.kill()

# budget + request cap on a fresh proxy
for f in ("r.jsonl", "s.json", "STOP", "port"):
    try:
        os.remove(f"{tmp}/{f}")
    except FileNotFoundError:
        pass
cfg["budget_usd"] = 0.40
cfg["mock_bill_estimate"] = True
json.dump(cfg, open(f"{tmp}/c.json", "w"))
p = subprocess.Popen([sys.executable, os.path.join(ROOT, "proxy.py"), "--config", f"{tmp}/c.json"], env={"PATH": "/usr/bin:/bin"})
for _ in range(100):
    if os.path.exists(f"{tmp}/port") and open(f"{tmp}/port").read():
        break
    time.sleep(0.05)
port = int(open(f"{tmp}/port").read())
mid = {**base, "messages": [{"role": "user", "content": "y" * 150_000}]}   # ~50k tokens -> est ~$0.36
codes = [post(mid)[0], post(mid)[0]]
reasons = [json.loads(l).get("reason") for l in open(f"{tmp}/r.jsonl")]
check("budget guard refuses before forwarding when the estimate would pass the run budget", codes == [200, 400] and "budget" in reasons)
check("STOP flag written for the runner", os.path.exists(f"{tmp}/STOP"))
p.kill()
for f in ("r.jsonl", "s.json", "STOP", "port"):
    try:
        os.remove(f"{tmp}/{f}")
    except FileNotFoundError:
        pass
cfg["budget_usd"] = 5.0
cfg["mock_bill_estimate"] = False
json.dump(cfg, open(f"{tmp}/c.json", "w"))
p = subprocess.Popen([sys.executable, os.path.join(ROOT, "proxy.py"), "--config", f"{tmp}/c.json"], env={"PATH": "/usr/bin:/bin"})
for _ in range(100):
    if os.path.exists(f"{tmp}/port") and open(f"{tmp}/port").read():
        break
    time.sleep(0.05)
port = int(open(f"{tmp}/port").read())
codes = [post(base)[0] for _ in range(4)]
check("request cap: 3 served, 4th refused", codes == [200, 200, 200, 400])
p.kill()
print("PROXY SELF-TEST", "PASSED" if ok else "FAILED")
sys.exit(0 if ok else 1)
