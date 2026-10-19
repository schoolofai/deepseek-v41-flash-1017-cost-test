#!/usr/bin/env python3
"""Local metering proxy for the SCO-637 harness-vs-harness test.

Every harness (Claude Code, Codex CLI, OpenCode) is pointed at this proxy on 127.0.0.1 and the
proxy forwards to https://openrouter.ai. Doing it here, not in each tool, gives every harness the
same rules:

  * provider pin: body.provider = {only:[pin], order:[pin], allow_fallbacks:false} on EVERY
    model request (DeepSeek -> "deepseek", Sonnet -> "anthropic", GPT -> "openai"); any
    service_tier / speed field is stripped so no premium tier endpoint can be picked
  * wrong model -> refused (a harness cannot quietly call a different, pricier model)
  * output clamp: max output tokens per request <= max_output_tokens
  * request cap: at most max_requests model requests per run (the uniform "turn" limit)
  * budget guard: before forwarding, a conservative cost estimate for this request is checked
    against the run budget; if it does not fit, the request is refused and the run is stopped
  * metering: usage (tokens in / cached / cache-write / out / reasoning, OpenRouter's usage.cost)
    and generation ids are recorded for every request; the runner reconciles them afterwards
    with GET /api/v1/generation?id=...

mode "mock": nothing is forwarded anywhere. The proxy answers like a model would (first a
shell tool call that runs the visible tests, then a short final message), in the protocol each
harness speaks. This lets the dry run prove that each CLI starts, reads its config, sends its
requests to the right place with the right model and auth header, and runs a tool in the repo,
all for $0.

The proxy NEVER logs request headers, the Authorization value or the key. It does not read any
key itself; it just passes the harness's own Authorization header through to OpenRouter.
"""
import argparse
import http.client
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
CFG = {}
STATE = {"requests": 0, "refused": 0, "spent_usd": 0.0, "reserved_usd": 0.0, "stopped": False,
         "stop_reason": None, "gen_ids": [], "strict": False, "prev_in_tokens": 0,
         "prev_cache_ok": False, "prev_t": 0.0, "bytes_per_token": 3.0, "mock_turns": 0}
PASS_HEADERS_DROP = {"host", "content-length", "accept-encoding", "connection", "transfer-encoding",
                     "keep-alive", "proxy-connection"}


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log(rec):
    rec["t"] = now()
    with open(CFG["log"], "a") as f:
        f.write(json.dumps(rec) + "\n")


def save_state():
    tmp = CFG["state"] + ".tmp"
    with open(tmp, "w") as f:
        json.dump(STATE, f, indent=1)
    os.replace(tmp, CFG["state"])


def stop(reason):
    STATE["stopped"] = True
    STATE["stop_reason"] = STATE["stop_reason"] or reason
    with open(CFG["stop_flag"], "w") as f:
        f.write(reason + "\n")


def api_of(path):
    if path.endswith("/chat/completions"):
        return "chat"
    if path.endswith("/messages"):
        return "messages"
    if path.endswith("/responses"):
        return "responses"
    if path.endswith("/messages/count_tokens"):
        return "count_tokens"
    return None


# ----------------------------------------------------------------------------- request shaping

def describe(api, body):
    """Facts about the request for the fairness log (no content beyond sizes and tool names)."""
    tools = body.get("tools") or []
    names = []
    for t in tools:
        if api == "chat":
            names.append((t.get("function") or {}).get("name") or t.get("type"))
        else:
            names.append(t.get("name") or t.get("type"))
    sys_chars = 0
    if api == "messages":
        s = body.get("system")
        sys_chars = len(s) if isinstance(s, str) else sum(len(b.get("text", "")) for b in (s or []) if isinstance(b, dict))
    elif api == "chat":
        for m in body.get("messages", []):
            if m.get("role") in ("system", "developer"):
                c = m.get("content")
                sys_chars += len(c) if isinstance(c, str) else sum(len(p.get("text", "")) for p in (c or []) if isinstance(p, dict))
    elif api == "responses":
        sys_chars = len(body.get("instructions") or "")
        for it in body.get("input") or []:
            if isinstance(it, dict) and it.get("role") in ("system", "developer"):
                c = it.get("content")
                sys_chars += len(c) if isinstance(c, str) else sum(len(p.get("text", "")) for p in (c or []) if isinstance(p, dict))
    return {"tools_count": len(tools), "tool_names": names, "tools_bytes": len(json.dumps(tools)),
            "system_chars": sys_chars, "stream": bool(body.get("stream"))}


def clamp(api, body, cap):
    before = None
    if api == "chat":
        for k in ("max_completion_tokens", "max_tokens"):
            if k in body:
                before = body[k]
                body[k] = min(int(body[k]), cap)
        if before is None:
            body["max_tokens"] = cap
    elif api == "messages":
        before = body.get("max_tokens")
        body["max_tokens"] = min(int(before or cap), cap)
        th = body.get("thinking")
        if isinstance(th, dict) and th.get("budget_tokens") and th["budget_tokens"] >= body["max_tokens"]:
            th["budget_tokens"] = max(1024, body["max_tokens"] - 1024)
    elif api == "responses":
        before = body.get("max_output_tokens")
        body["max_output_tokens"] = min(int(before or cap), cap)
    return before


def estimate(body_bytes, max_out):
    """Conservative cost estimate for one request (USD)."""
    p = CFG["prices"]
    est_in = int(body_bytes / STATE["bytes_per_token"]) + 1
    fresh_rate = CFG["input_guard_rate"]
    if STATE["strict"] or not STATE["prev_cache_ok"] or time.time() - STATE["prev_t"] > 240:
        cost_in = est_in * fresh_rate
    else:
        prefix = min(est_in, STATE["prev_in_tokens"])
        cost_in = prefix * p["cache_read"] + (est_in - prefix) * fresh_rate
    return est_in, (cost_in + max_out * p["out"]) / 1e6


# ----------------------------------------------------------------------------- usage parsing

def norm_usage(api, u):
    if not u:
        return None
    if api == "messages":
        cr = u.get("cache_read_input_tokens") or 0
        cw = u.get("cache_creation_input_tokens") or 0
        fresh = u.get("input_tokens") or 0
        return {"in_total": fresh + cr + cw, "cache_read": cr, "cache_write": cw, "out": u.get("output_tokens") or 0,
                "reasoning": None, "cost": u.get("cost")}
    if api == "responses":
        d = u.get("input_tokens_details") or {}
        o = u.get("output_tokens_details") or {}
        return {"in_total": u.get("input_tokens") or 0, "cache_read": d.get("cached_tokens") or 0,
                "cache_write": d.get("cache_write_tokens") or 0, "out": u.get("output_tokens") or 0,
                "reasoning": o.get("reasoning_tokens"), "cost": u.get("cost")}
    d = u.get("prompt_tokens_details") or {}
    o = u.get("completion_tokens_details") or {}
    return {"in_total": u.get("prompt_tokens") or 0, "cache_read": d.get("cached_tokens") or 0,
            "cache_write": d.get("cache_write_tokens") or 0, "out": u.get("completion_tokens") or 0,
            "reasoning": o.get("reasoning_tokens"), "cost": u.get("cost")}


def price_usage(nu):
    p = CFG["prices"]
    fresh = max(0, nu["in_total"] - nu["cache_read"] - nu["cache_write"])
    cw_rate = CFG.get("cache_write_guard_rate", p.get("cache_write", p["in"]))
    return (fresh * p["in"] + nu["cache_read"] * p["cache_read"] + nu["cache_write"] * cw_rate + nu["out"] * p["out"]) / 1e6


class SSEScan:
    """Pulls ids and usage out of an SSE stream as it passes through."""

    def __init__(self, api):
        self.api, self.buf, self.ids, self.usage, self.msg_usage = api, b"", [], None, {}

    def feed(self, chunk):
        self.buf += chunk
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            line = line.strip()
            if line.startswith(b"data:"):
                data = line[5:].strip()
                if data and data != b"[DONE]":
                    try:
                        self.event(json.loads(data))
                    except ValueError:
                        pass

    def event(self, ev):
        if not isinstance(ev, dict):
            return
        if self.api == "messages":
            t = ev.get("type")
            if t == "message_start":
                m = ev.get("message") or {}
                if m.get("id"):
                    self.ids.append(m["id"])
                self.msg_usage.update(m.get("usage") or {})
            elif t == "message_delta":
                self.msg_usage.update({k: v for k, v in (ev.get("usage") or {}).items() if v is not None})
            if self.msg_usage:
                self.usage = dict(self.msg_usage)
        elif self.api == "responses":
            r = ev.get("response") or {}
            if r.get("id") and r["id"] not in self.ids:
                self.ids.append(r["id"])
            if r.get("usage"):
                self.usage = r["usage"]
        else:
            if ev.get("id") and ev["id"] not in self.ids:
                self.ids.append(ev["id"])
            if ev.get("usage"):
                self.usage = ev["usage"]


def scan_json(api, obj):
    ids = [obj["id"]] if isinstance(obj, dict) and obj.get("id") else []
    return ids, (obj.get("usage") if isinstance(obj, dict) else None)


# ----------------------------------------------------------------------------- mock model

MOCK_CMD = "python -m pytest -q 2>&1 | tail -3"


def has_tool_result(api, body):
    if api == "chat":
        return any(m.get("role") == "tool" for m in body.get("messages", []))
    if api == "messages":
        for m in body.get("messages", []):
            c = m.get("content")
            if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                return True
        return False
    for it in body.get("input") or []:
        if isinstance(it, dict) and str(it.get("type", "")).endswith("_output"):
            return True
    return False


def tool_result_preview(api, body):
    try:
        if api == "chat":
            ms = [m for m in body.get("messages", []) if m.get("role") == "tool"]
            if not ms:
                return None
            c = ms[-1].get("content")
            return (c if isinstance(c, str) else json.dumps(c))[:400]
        if api == "messages":
            for m in reversed(body.get("messages", [])):
                for b in m.get("content") if isinstance(m.get("content"), list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        c = b.get("content")
                        return (c if isinstance(c, str) else json.dumps(c))[:400]
        for it in reversed(body.get("input") or []):
            if isinstance(it, dict) and str(it.get("type", "")).endswith("_output"):
                o = it.get("output")
                return (o if isinstance(o, str) else json.dumps(o))[:400]
    except Exception as e:  # noqa: BLE001
        return f"(preview error {e})"
    return None


def pick_shell_tool(api, body):
    best = None
    for t in body.get("tools") or []:
        if api == "chat":
            fn = t.get("function") or {}
            name, schema = fn.get("name"), fn.get("parameters") or {}
        elif api == "messages":
            name, schema = t.get("name"), t.get("input_schema") or {}
        else:
            if t.get("type") == "local_shell":
                return "local_shell", {}
            name, schema = t.get("name"), t.get("parameters") or {}
        if not name:
            continue
        low = name.lower()
        rank = 0 if low in ("bash", "shell", "exec_command", "shell_command") else (1 if ("bash" in low or "shell" in low or "exec" in low) else None)
        if rank is not None and (best is None or rank < best[0]):
            best = (rank, name, schema)
    return (best[1], best[2]) if best else (None, None)


def shell_args(schema):
    props = (schema or {}).get("properties") or {}
    req = (schema or {}).get("required") or []
    args = {}
    for k, v in props.items():
        typ = v.get("type")
        if k in ("command", "cmd"):
            args[k] = ["bash", "-lc", MOCK_CMD] if typ == "array" else MOCK_CMD
        elif k == "description":
            args[k] = "dry-run check: run the visible tests"
        elif k in req:
            args[k] = {"string": "", "integer": 60000, "number": 60000, "boolean": False, "array": []}.get(typ, "")
    return args


def sse(event_type, data):
    head = f"event: {event_type}\n" if event_type else ""
    return (head + "data: " + json.dumps(data) + "\n\n").encode()


def mock_reply(api, body):
    model = body.get("model")
    final = has_tool_result(api, body)
    tool, schema = (None, None) if final else pick_shell_tool(api, body)
    text = "MOCK (dry run): no model was called. The visible tests ran; nothing else to do."
    stream = bool(body.get("stream"))
    rid = "mock-" + uuid.uuid4().hex[:12]
    zero_u = {"input_tokens": 0, "output_tokens": 0}
    if api == "count_tokens":
        return "application/json", json.dumps({"input_tokens": 1}).encode(), "count_tokens"
    if api == "messages":
        if tool:
            block = {"type": "tool_use", "id": "toolu_" + rid, "name": tool, "input": shell_args(schema)}
            stop_reason, kind = "tool_use", f"tool_call:{tool}"
        else:
            block = {"type": "text", "text": text}
            stop_reason, kind = "end_turn", "final_text"
        if not stream:
            msg = {"id": rid, "type": "message", "role": "assistant", "model": model, "content": [block],
                   "stop_reason": stop_reason, "stop_sequence": None, "usage": zero_u}
            return "application/json", json.dumps(msg).encode(), kind
        out = sse("message_start", {"type": "message_start", "message": {"id": rid, "type": "message", "role": "assistant", "model": model,
                                                                         "content": [], "stop_reason": None, "stop_sequence": None, "usage": zero_u}})
        if tool:
            out += sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {**block, "input": {}}})
            out += sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}})
        else:
            out += sse("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
            out += sse("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}})
        out += sse("content_block_stop", {"type": "content_block_stop", "index": 0})
        out += sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": 0}})
        out += sse("message_stop", {"type": "message_stop"})
        return "text/event-stream", out, kind
    if api == "responses":
        usage = {"input_tokens": 0, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 0,
                 "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 0}
        if tool == "local_shell":
            item = {"type": "local_shell_call", "id": "lsh_" + rid, "call_id": "call_" + rid, "status": "completed",
                    "action": {"type": "exec", "command": ["bash", "-lc", MOCK_CMD]}}
            kind = "tool_call:local_shell"
        elif tool:
            item = {"type": "function_call", "id": "fc_" + rid, "call_id": "call_" + rid, "name": tool,
                    "arguments": json.dumps(shell_args(schema)), "status": "completed"}
            kind = f"tool_call:{tool}"
        else:
            item = {"type": "message", "id": "msg_" + rid, "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text, "annotations": []}]}
            kind = "final_text"
        resp = {"id": "resp_" + rid, "object": "response", "created_at": int(time.time()), "model": model,
                "status": "completed", "output": [item], "usage": usage}
        if not stream:
            return "application/json", json.dumps(resp).encode(), kind
        out = sse("response.created", {"type": "response.created", "response": {**resp, "status": "in_progress", "output": [], "usage": None}})
        out += sse("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": item})
        if item["type"] == "message":
            out += sse("response.output_text.delta", {"type": "response.output_text.delta", "item_id": item["id"], "output_index": 0, "content_index": 0, "delta": text})
            out += sse("response.output_text.done", {"type": "response.output_text.done", "item_id": item["id"], "output_index": 0, "content_index": 0, "text": text})
        out += sse("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item})
        out += sse("response.completed", {"type": "response.completed", "response": resp})
        return "text/event-stream", out, kind
    # chat completions
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0}
    if tool:
        delta = {"role": "assistant", "content": None, "tool_calls": [{"index": 0, "id": "call_" + rid, "type": "function",
                                                                      "function": {"name": tool, "arguments": json.dumps(shell_args(schema))}}]}
        finish, kind = "tool_calls", f"tool_call:{tool}"
    else:
        delta = {"role": "assistant", "content": text}
        finish, kind = "stop", "final_text"
    if not stream:
        msg = {k: v for k, v in delta.items()}
        obj = {"id": "gen-" + rid, "object": "chat.completion", "created": int(time.time()), "model": model,
               "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": usage}
        return "application/json", json.dumps(obj).encode(), kind
    base = {"id": "gen-" + rid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
    out = ("data: " + json.dumps({**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}) + "\n\n").encode()
    out += ("data: " + json.dumps({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage}) + "\n\n").encode()
    out += b"data: [DONE]\n\n"
    return "text/event-stream", out, kind


# ----------------------------------------------------------------------------- HTTP handler

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "sco637-meter/1"

    def log_message(self, *a):  # silence default stderr logging (it would include paths only, but keep quiet)
        pass

    def send_json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def refuse(self, api, reason, msg, rec):
        rec.update({"decision": "refused", "reason": reason})
        log(rec)
        if api == "messages":
            body = {"type": "error", "error": {"type": "invalid_request_error", "message": f"[sco637 meter] {msg}"}}
        else:
            body = {"error": {"type": "invalid_request_error", "code": reason, "message": f"[sco637 meter] {msg}"}}
        self.send_json(400, body)

    def auth_facts(self):
        a = self.headers.get("Authorization")
        x = self.headers.get("x-api-key")
        facts = {"auth_header": "authorization" if a else ("x-api-key" if x else None)}
        if CFG["mode"] == "mock":
            dummy = os.environ.get("SCO637_DRYRUN_DUMMY", "")
            val = (a or x or "").replace("Bearer ", "", 1)
            facts["auth_is_dryrun_dummy"] = bool(dummy) and val == dummy
        return facts

    def do_GET(self):
        path = self.path.split("?")[0]
        rec = {"method": "GET", "path": path, "query": self.path.partition("?")[2][:200]}
        if not path.startswith("/api/"):
            rec["decision"] = "refused_path"
            log(rec)
            return self.send_json(404, {"error": "not found"})
        if CFG["mode"] == "mock":
            if path.startswith("/api/v1/models"):
                # public, free catalog endpoint: fetched WITHOUT any auth header so the dry run sees
                # the same model metadata a live run would (Codex sizes its tools/effort from it)
                return self.forward(None, rec, body_bytes=None, public=True)
            rec["decision"] = "mock_empty_list"
            log(rec)
            return self.send_json(200, {"data": [], "object": "list"})
        self.forward(None, rec, body_bytes=None)

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        path = self.path.split("?")[0]
        api = api_of(path)
        rec = {"method": "POST", "path": path, "api": api, **self.auth_facts()}
        if not path.startswith("/api/") or api is None:
            return self.refuse(api, "unknown_path", f"path {path} not allowed", rec)
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return self.refuse(api, "bad_json", "body is not JSON", rec)
        rec["model"] = body.get("model")
        if api == "count_tokens":
            if CFG["mode"] == "mock":
                rec["decision"] = "mock"
                log(rec)
                return self.send_json(200, {"input_tokens": int(len(raw) / 3)})
            return self.forward(api, rec, raw)
        if body.get("model") != CFG["model"]:
            STATE["refused"] += 1
            return self.refuse(api, "wrong_model", f"model {body.get('model')!r} is not the model under test", rec)
        rec.update(describe(api, body))
        rec["body_keys"] = sorted(body.keys())
        if CFG["mode"] == "mock" and CFG.get("dump_bodies_dir"):
            os.makedirs(CFG["dump_bodies_dir"], exist_ok=True)
            with open(os.path.join(CFG["dump_bodies_dir"], f"req{STATE['requests'] + 1:03d}.json"), "w") as f:
                json.dump(body, f, indent=1)
        for k in ("service_tier", "speed"):
            if k in body:
                rec[f"stripped_{k}"] = body.pop(k)
        if "provider" in body:
            rec["harness_sent_provider"] = body["provider"]
        body["provider"] = {"only": [CFG["pin"]], "order": [CFG["pin"]], "allow_fallbacks": False}
        rec["provider_pin"] = CFG["pin"]
        rec["max_out_requested"] = clamp(api, body, CFG["max_output_tokens"])
        rec["max_out_clamped"] = CFG["max_output_tokens"]
        new_raw = json.dumps(body).encode()
        with LOCK:
            if STATE["stopped"]:
                return self.refuse(api, "run_stopped", f"run already stopped ({STATE['stop_reason']})", rec)
            if STATE["requests"] >= CFG["max_requests"]:
                stop("request_cap")
                save_state()
                return self.refuse(api, "request_cap", f"request cap {CFG['max_requests']} reached", rec)
            est_in, est_cost = estimate(len(new_raw), CFG["max_output_tokens"])
            rec.update({"est_in_tokens": est_in, "est_cost_usd": round(est_cost, 6), "guard_strict": STATE["strict"]})
            if est_in > CFG["max_input_tokens"]:
                stop("context_cap")
                save_state()
                return self.refuse(api, "context_cap", f"estimated {est_in} input tokens > cap {CFG['max_input_tokens']}", rec)
            if STATE["spent_usd"] + STATE["reserved_usd"] + est_cost > CFG["budget_usd"]:
                stop("budget")
                save_state()
                return self.refuse(api, "budget", f"run budget ${CFG['budget_usd']:.2f} would be exceeded "
                                   f"(spent {STATE['spent_usd']:.4f} + this request up to {est_cost:.4f})", rec)
            STATE["requests"] += 1
            STATE["reserved_usd"] += est_cost
            rec["n"] = STATE["requests"]
            save_state()
        try:
            if CFG["mode"] == "mock":
                rec["tool_result_seen"] = tool_result_preview(api, body)
                ctype, data, kind = mock_reply(api, body)
                rec.update({"decision": "mock", "mock_reply": kind})
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                with LOCK:
                    STATE["reserved_usd"] -= est_cost
                    STATE["mock_turns"] += 1
                    if CFG.get("mock_bill_estimate"):  # self-test only: pretend the estimate was spent
                        STATE["spent_usd"] += est_cost
                    save_state()
                log(rec)
                return
            self.forward(api, rec, new_raw, est_cost=est_cost, est_in=est_in)
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)[:300]
            with LOCK:
                STATE["reserved_usd"] -= est_cost
                # unknown outcome: book the estimate as spent (conservative)
                STATE["spent_usd"] += est_cost
                save_state()
            log(rec)

    def forward(self, api, rec, body_bytes, est_cost=0.0, est_in=0, public=False):
        if CFG["mode"] != "live" and not (public and self.command == "GET"):
            return self.send_json(500, {"error": "not live"})
        headers = {k: v for k, v in self.headers.items() if k.lower() not in PASS_HEADERS_DROP}
        if public:
            headers = {k: v for k, v in headers.items() if k.lower() not in ("authorization", "x-api-key", "cookie")}
        headers["Accept-Encoding"] = "identity"
        if body_bytes is not None:
            headers["Content-Length"] = str(len(body_bytes))
        t0 = time.time()
        conn = http.client.HTTPSConnection(CFG["upstream_host"], 443, timeout=900)
        conn.request(self.command, self.path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        rec["status"] = resp.status
        self.send_response(resp.status)
        ctype = resp.getheader("Content-Type", "")
        for k, v in resp.getheaders():
            if k.lower() in ("content-type", "x-generation-id", "x-request-id", "retry-after"):
                self.send_header(k, v)
            if "generation" in k.lower():
                rec.setdefault("hdr_gen_ids", []).append(v)
        self.end_headers()
        scan = SSEScan(api) if "event-stream" in ctype else None
        whole = b""
        ttfb = None
        while True:
            chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
            if not chunk:
                break
            if ttfb is None:
                ttfb = time.time() - t0
            self.wfile.write(chunk)
            self.wfile.flush()
            if scan:
                scan.feed(chunk)
            elif len(whole) < 5_000_000:
                whole += chunk
        conn.close()
        rec["latency_s"] = round(time.time() - t0, 3)
        rec["ttfb_s"] = round(ttfb or 0, 3)
        if api is None or api == "count_tokens":
            rec["decision"] = "forwarded_free_public_no_auth" if public else "forwarded_free"
            rec["bytes"] = len(whole)
            log(rec)
            return
        if scan:
            ids, usage = scan.ids, scan.usage
        else:
            try:
                ids, usage = scan_json(api, json.loads(whole or b"{}"))
            except ValueError:
                ids, usage = [], None
        nu = norm_usage(api, usage)
        with LOCK:
            STATE["reserved_usd"] -= est_cost
            if nu:
                actual = nu["cost"] if isinstance(nu.get("cost"), (int, float)) else price_usage(nu)
                rec["cost_source"] = "openrouter_usage.cost" if isinstance(nu.get("cost"), (int, float)) else "computed_from_prices"
                if actual > est_cost * 1.05 + 1e-6:
                    STATE["strict"] = True  # estimate was too low (e.g. cache miss): go fully conservative
                if nu["in_total"] > 0 and est_in > 0:
                    ratio = len(body_bytes) / nu["in_total"]
                    STATE["bytes_per_token"] = max(1.5, min(STATE["bytes_per_token"], ratio * 0.9))
                STATE["prev_in_tokens"] = nu["in_total"]
                STATE["prev_cache_ok"] = nu["in_total"] > 0 and nu["cache_read"] >= 0.5 * nu["in_total"]
            else:
                actual = est_cost if resp.status < 400 else 0.0
                rec["cost_source"] = "no_usage_booked_estimate" if resp.status < 400 else "error_status_zero"
            STATE["spent_usd"] += actual
            STATE["prev_t"] = time.time()
            STATE["gen_ids"].extend(ids + rec.get("hdr_gen_ids", []))
            rec.update({"decision": "forwarded", "usage": nu, "cost_usd": round(actual, 6), "gen_ids": ids,
                        "run_spent_usd": round(STATE["spent_usd"], 6)})
            if STATE["spent_usd"] >= CFG["budget_usd"]:
                stop("budget")
            save_state()
        log(rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    CFG.update(json.load(open(args.config)))
    assert CFG["mode"] in ("mock", "live")
    if CFG["mode"] == "live":
        assert CFG["upstream_host"] == "openrouter.ai", "live mode only talks to openrouter.ai"
    srv = ThreadingHTTPServer(("127.0.0.1", CFG.get("listen_port", 0)), Handler)
    with open(CFG["port_file"], "w") as f:
        f.write(str(srv.server_address[1]))
    save_state()
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main())
