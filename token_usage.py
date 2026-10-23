"""Token usage analysis for Claude Code transcripts.

Claude Code writes one JSONL transcript per session under
~/.claude/projects/<project>/<session>.jsonl. Each assistant entry carries the
API `usage` block for that request. This module parses those files and builds
the aggregates and insights that the /tokens dashboard renders.

Set CLAUDE_LOGS_DIR to read transcripts from somewhere else.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

LOGS_DIR = Path(os.environ.get("CLAUDE_LOGS_DIR", Path.home() / ".claude" / "projects"))

# USD per million tokens: (input, output, cache read). Cache writes are priced
# off input: 1.25x for the 5-minute TTL, 2x for the 1-hour TTL.
# Longest prefix wins, so "claude-opus-5-5" matches before "claude-opus-5".
PRICING = {
    "claude-fable-5-1": (10.00, 50.00, 0.25),
    "claude-mythos-5-1": (10.00, 50.00, 0.25),
    "claude-fable-5": (10.00, 50.00, 1.00),
    "claude-mythos-5": (10.00, 50.00, 1.00),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4": (5.00, 25.00, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-sonnet-4": (3.00, 15.00, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4": (1.00, 5.00, 0.10),
}
# Haiku 5.5 bills prompts above 100K tokens at a higher tier.
HAIKU_55_LONG = (0.50, 2.50, 0.05)
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.0
LARGE_CONTEXT = 200_000
CHARS_PER_TOKEN = 4  # rough estimate for tool-result text


def price_for(model, prompt_tokens):
    for prefix in sorted(PRICING, key=len, reverse=True):
        if model.startswith(prefix):
            if prefix == "claude-haiku-5-5" and prompt_tokens > 100_000:
                return HAIKU_55_LONG
            return PRICING[prefix]
    return None


def request_cost(model, u):
    """Return (cost, cost_without_cache) in USD, or (None, None) if unpriced."""
    prompt = u["input"] + u["cache_write"] + u["cache_read"]
    p = price_for(model, prompt)
    if p is None:
        return None, None
    inp, out, read = (x / 1_000_000 for x in p)
    cost = (
        u["input"] * inp
        + u["cache_write_5m"] * inp * CACHE_WRITE_5M
        + u["cache_write_1h"] * inp * CACHE_WRITE_1H
        + u["cache_read"] * read
        + u["output"] * out
    )
    uncached = prompt * inp + u["output"] * out
    return cost, uncached


def _usage(raw):
    cw = raw.get("cache_creation_input_tokens", 0) or 0
    split = raw.get("cache_creation") or {}
    cw_1h = split.get("ephemeral_1h_input_tokens", 0) or 0
    cw_5m = split.get("ephemeral_5m_input_tokens", cw - cw_1h) or 0
    return {
        "input": raw.get("input_tokens", 0) or 0,
        "cache_write": cw,
        "cache_write_5m": cw_5m,
        "cache_write_1h": cw_1h,
        "cache_read": raw.get("cache_read_input_tokens", 0) or 0,
        "output": raw.get("output_tokens", 0) or 0,
        "thinking": (raw.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0,
        "web_search": (raw.get("server_tool_use") or {}).get("web_search_requests", 0) or 0,
    }


def _text_len(content):
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_text_len(c.get("text") or c.get("content") or "") for c in content if isinstance(c, dict))
    return 0


def _project_name(path):
    rel = path.relative_to(LOGS_DIR)
    return rel.parts[0].lstrip("-").replace("-", "/") if len(rel.parts) > 1 else "(root)"


def load_requests(logs_dir=None):
    """Parse every transcript into one record per API request, plus tool stats."""
    base = Path(logs_dir) if logs_dir else LOGS_DIR
    requests = {}
    tool_calls = {}  # tool_use_id -> tool name
    tool_stats = defaultdict(lambda: {"calls": 0, "result_chars": 0, "errors": 0})
    if not base.exists():
        return [], {}

    for path in sorted(base.rglob("*.jsonl")):
        project = _project_name(path) if base == LOGS_DIR else path.parent.name
        is_subagent = "subagents" in path.parts
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = entry.get("message") or {}
            content = msg.get("content") if isinstance(msg.get("content"), list) else []

            if entry.get("type") == "assistant" and msg.get("usage"):
                model = msg.get("model") or "unknown"
                if model == "<synthetic>":
                    continue
                # Claude Code writes one line per content block; they share the
                # message id and usage, so key on it to avoid double counting.
                key = msg.get("id") or entry.get("requestId") or entry.get("uuid")
                rec = requests.setdefault(key, {
                    "id": key,
                    "session": entry.get("sessionId") or path.stem,
                    "project": project,
                    "subagent": is_subagent or bool(entry.get("isSidechain")),
                    "timestamp": entry.get("timestamp"),
                    "model": model,
                    "tools": [],
                })
                rec["usage"] = _usage(msg["usage"])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name", "?")
                        if block.get("id") not in tool_calls:
                            tool_calls[block.get("id")] = name
                            tool_stats[name]["calls"] += 1
                            rec["tools"].append(name)

            elif entry.get("type") == "user":
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        name = tool_calls.get(block.get("tool_use_id"), "?")
                        tool_stats[name]["result_chars"] += _text_len(block.get("content"))
                        if block.get("is_error"):
                            tool_stats[name]["errors"] += 1

    out = []
    for rec in requests.values():
        if "usage" not in rec:
            continue
        rec["cost"], rec["uncached_cost"] = request_cost(rec["model"], rec["usage"])
        u = rec["usage"]
        rec["context"] = u["input"] + u["cache_write"] + u["cache_read"]
        rec["total"] = rec["context"] + u["output"]
        out.append(rec)
    out.sort(key=lambda r: r["timestamp"] or "")
    return out, dict(tool_stats)


def _blank():
    return {"requests": 0, "input": 0, "cache_write": 0, "cache_read": 0,
            "output": 0, "thinking": 0, "total": 0, "cost": 0.0}


def _add(bucket, rec):
    u = rec["usage"]
    bucket["requests"] += 1
    for k in ("input", "cache_write", "cache_read", "output", "thinking"):
        bucket[k] += u[k]
    bucket["total"] += rec["total"]
    bucket["cost"] += rec["cost"] or 0.0


def _local(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (AttributeError, ValueError):
        return None


def _pct(part, whole):
    return 100.0 * part / whole if whole else 0.0


def _fmt(n):
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= size:
            return f"{n / size:.1f}{unit}"
    return str(int(n))


def analyze(logs_dir=None, days=None):
    reqs, tool_stats = load_requests(logs_dir)
    if days:
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        reqs = [r for r in reqs if (_local(r["timestamp"]) or datetime.min.replace(tzinfo=timezone.utc)).timestamp() >= cutoff]

    totals = _blank()
    by_day, by_hour = defaultdict(_blank), defaultdict(_blank)
    by_model, by_session, by_project = defaultdict(_blank), defaultdict(_blank), defaultdict(_blank)
    session_meta = {}
    cw_1h = cw_5m = web_search = unpriced = 0
    uncached_cost = 0.0
    contexts = []

    for r in reqs:
        _add(totals, r)
        dt = _local(r["timestamp"])
        if dt:
            _add(by_day[dt.strftime("%Y-%m-%d")], r)
            _add(by_hour[dt.hour], r)
        _add(by_model[r["model"]], r)
        _add(by_session[r["session"]], r)
        _add(by_project[r["project"]], r)
        meta = session_meta.setdefault(r["session"], {
            "project": r["project"], "start": r["timestamp"], "end": r["timestamp"],
            "max_context": 0, "subagent_requests": 0})
        meta["end"] = r["timestamp"] or meta["end"]
        meta["max_context"] = max(meta["max_context"], r["context"])
        meta["subagent_requests"] += r["subagent"]
        cw_1h += r["usage"]["cache_write_1h"]
        cw_5m += r["usage"]["cache_write_5m"]
        web_search += r["usage"]["web_search"]
        contexts.append(r["context"])
        if r["cost"] is None:
            unpriced += 1
        else:
            uncached_cost += r["uncached_cost"]

    prompt = totals["input"] + totals["cache_write"] + totals["cache_read"]
    cost_parts = _cost_by_type(reqs)

    sessions = []
    for sid, b in by_session.items():
        m = session_meta[sid]
        sessions.append({"session": sid, **b, **m})
    sessions.sort(key=lambda s: s["cost"], reverse=True)

    tools = []
    for name, s in tool_stats.items():
        est = s["result_chars"] // CHARS_PER_TOKEN
        tools.append({"tool": name, "calls": s["calls"], "errors": s["errors"],
                      "result_tokens_est": est,
                      "avg_result_tokens": est // s["calls"] if s["calls"] else 0})
    tools.sort(key=lambda t: t["result_tokens_est"], reverse=True)

    top = sorted(reqs, key=lambda r: r["cost"] or 0, reverse=True)[:15]

    summary = {
        **totals,
        "prompt": prompt,
        "sessions": len(by_session),
        "projects": len(by_project),
        "cache_hit_rate": _pct(totals["cache_read"], prompt),
        "uncached_cost": uncached_cost,
        "cache_savings": uncached_cost - totals["cost"],
        "cache_write_1h": cw_1h,
        "cache_write_5m": cw_5m,
        "web_search_requests": web_search,
        "avg_context": sum(contexts) / len(contexts) if contexts else 0,
        "max_context": max(contexts, default=0),
        "large_context_requests": sum(c > LARGE_CONTEXT for c in contexts),
        "avg_output": totals["output"] / totals["requests"] if totals["requests"] else 0,
        "unpriced_requests": unpriced,
        "first": reqs[0]["timestamp"] if reqs else None,
        "last": reqs[-1]["timestamp"] if reqs else None,
        "cost_by_type": cost_parts,
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "logs_dir": str(Path(logs_dir) if logs_dir else LOGS_DIR),
        "summary": summary,
        "by_day": [{"day": d, **b} for d, b in sorted(by_day.items())],
        "by_hour": [{"hour": h, **by_hour.get(h, _blank())} for h in range(24)],
        "by_model": sorted(({"model": k, **v} for k, v in by_model.items()), key=lambda x: x["cost"], reverse=True),
        "by_project": sorted(({"project": k, **v} for k, v in by_project.items()), key=lambda x: x["cost"], reverse=True),
        "sessions": sessions[:50],
        "tools": tools,
        "top_requests": [{
            "timestamp": r["timestamp"], "session": r["session"], "model": r["model"],
            "context": r["context"], "output": r["usage"]["output"], "cost": r["cost"],
            "tools": r["tools"], "subagent": r["subagent"]} for r in top],
        "insights": _insights(summary, sessions, tools, by_day, by_model),
    }


def _cost_by_type(reqs):
    parts = {"input": 0.0, "cache_write": 0.0, "cache_read": 0.0, "output": 0.0}
    for r in reqs:
        u = r["usage"]
        p = price_for(r["model"], r["context"])
        if p is None:
            continue
        inp, out, read = (x / 1_000_000 for x in p)
        parts["input"] += u["input"] * inp
        parts["cache_write"] += u["cache_write_5m"] * inp * CACHE_WRITE_5M + u["cache_write_1h"] * inp * CACHE_WRITE_1H
        parts["cache_read"] += u["cache_read"] * read
        parts["output"] += u["output"] * out
    return parts


def _insights(s, sessions, tools, by_day, by_model):
    """Plain-language findings, most important first. Each has a level for the icon."""
    out = []
    if not s["requests"]:
        return [{"level": "info", "text": f"No usage found. Point CLAUDE_LOGS_DIR at a folder of Claude Code .jsonl transcripts."}]

    parts = s["cost_by_type"]
    total_cost = sum(parts.values())
    if total_cost:
        driver = max(parts, key=parts.get)
        label = {"input": "uncached input", "cache_write": "cache writes",
                 "cache_read": "cache reads", "output": "output"}[driver]
        out.append({"level": "info", "text":
            f"{label.capitalize()} drive {_pct(parts[driver], total_cost):.0f}% of estimated spend "
            f"(${parts[driver]:.2f} of ${total_cost:.2f})."})

    hit = s["cache_hit_rate"]
    level = "good" if hit >= 80 else "warning" if hit >= 50 else "critical"
    out.append({"level": level, "text":
        f"Cache hit rate is {hit:.1f}%: {_fmt(s['cache_read'])} of {_fmt(s['prompt'])} prompt tokens came from cache, "
        f"saving about ${s['cache_savings']:.2f} versus no caching."})

    if s["cache_write"]:
        share_1h = _pct(s["cache_write_1h"], s["cache_write"])
        if share_1h > 50:
            out.append({"level": "info", "text":
                f"{share_1h:.0f}% of cache writes use the 1-hour TTL (billed at 2x input vs 1.25x for 5-minute). "
                f"That pays off only when you pause more than 5 minutes between turns."})
        reads_per_write = s["cache_read"] / s["cache_write"]
        if reads_per_write < 3:
            out.append({"level": "warning", "text":
                f"Each cached token is read only {reads_per_write:.1f}x on average. Short sessions or frequent context "
                f"changes (new files, edited CLAUDE.md, switching models) keep re-writing the cache."})

    if s["output"]:
        out.append({"level": "info", "text":
            f"Thinking is {_pct(s['thinking'], s['output']):.0f}% of output tokens "
            f"({_fmt(s['thinking'])} of {_fmt(s['output'])}); average output is {s['avg_output']:.0f} tokens per request."})

    out.append({"level": "warning" if s["avg_context"] > 150_000 else "info", "text":
        f"Average request carries {_fmt(s['avg_context'])} tokens of context (max {_fmt(s['max_context'])}). "
        + (f"{s['large_context_requests']} requests exceeded {_fmt(LARGE_CONTEXT)}; /compact or /clear between tasks keeps this down."
           if s["large_context_requests"] else "None exceeded 200K.")})

    if len(sessions) > 1 and total_cost:
        top = sessions[0]
        out.append({"level": "info", "text":
            f"Most expensive session ({top['session'][:8]}, {top['project']}) cost ${top['cost']:.2f}, "
            f"{_pct(top['cost'], s['cost']):.0f}% of the total, across {top['requests']} requests."})

    if tools:
        t = tools[0]
        out.append({"level": "info", "text":
            f"'{t['tool']}' returned the most text into context: ~{_fmt(t['result_tokens_est'])} tokens over "
            f"{t['calls']} calls (~{_fmt(t['avg_result_tokens'])} each). Narrower reads/searches shrink every later turn."})
        errs = sorted((x for x in tools if x["errors"]), key=lambda x: x["errors"], reverse=True)
        if errs:
            out.append({"level": "warning", "text":
                "Tool errors waste a round trip each: " + ", ".join(f"{x['tool']} ({x['errors']})" for x in errs[:4]) + "."})

    if len(by_day) > 1:
        day, b = max(by_day.items(), key=lambda kv: kv[1]["cost"])
        out.append({"level": "info", "text": f"Busiest day was {day}: ${b['cost']:.2f} over {b['requests']} requests."})

    if len(by_model) > 1:
        names = ", ".join(f"{m} {_pct(b['cost'], s['cost']):.0f}%" for m, b in sorted(by_model.items(), key=lambda kv: -kv[1]["cost"]))
        out.append({"level": "info", "text": f"Spend by model: {names}."})

    if s["unpriced_requests"]:
        out.append({"level": "warning", "text":
            f"{s['unpriced_requests']} requests used a model with no price in the table; they are excluded from cost."})
    return out
