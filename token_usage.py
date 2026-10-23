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
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGS_DIR = Path(os.environ.get("CLAUDE_LOGS_DIR", Path.home() / ".claude" / "projects"))
LIMITS_FILE = Path(os.environ.get("TOKEN_LIMITS_FILE", Path(__file__).with_name("limits.json")))

# Rolling windows a limit can apply to. Claude plans meter usage over a 5-hour
# session window and a weekly window but don't publish them as token counts,
# so the amounts are yours to set.
WINDOWS = {"5h": "Last 5 hours", "7d": "Last 7 days", "month": "This month"}
DEFAULT_LIMITS = {
    "count_cache_reads": False,
    "limits": {w: {"tokens": None, "cost": None} for w in WINDOWS},
}

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
    cw_1h = min(cw, split.get("ephemeral_1h_input_tokens", 0) or 0)
    cw_5m = cw - cw_1h
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
    """Parse every transcript into one record per API request.

    Each record lists the tools it called; tool results are attached to the
    request that made the call so they filter by date and project with it.
    """
    base = Path(logs_dir) if logs_dir else LOGS_DIR
    requests = {}
    tool_calls = {}  # tool_use_id -> (tool name, request record)
    if not base.exists():
        return []

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
                    "tool_results": [],  # (tool name, chars, is_error)
                })
                rec["usage"] = _usage(msg["usage"])
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name", "?")
                        if block.get("id") not in tool_calls:
                            tool_calls[block.get("id")] = (name, rec)
                            rec["tools"].append(name)

            elif entry.get("type") == "user":
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        call = tool_calls.get(block.get("tool_use_id"))
                        if call:
                            name, owner = call
                            owner["tool_results"].append(
                                (name, _text_len(block.get("content")), bool(block.get("is_error"))))

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
    return out


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


def _ts(r):
    dt = _local(r["timestamp"])
    return dt.timestamp() if dt else 0.0


def load_limits():
    try:
        saved = json.loads(LIMITS_FILE.read_text())
    except (OSError, ValueError):
        saved = {}
    out = json.loads(json.dumps(DEFAULT_LIMITS))
    out["count_cache_reads"] = bool(saved.get("count_cache_reads", out["count_cache_reads"]))
    for w in WINDOWS:
        for k in ("tokens", "cost"):
            v = (saved.get("limits") or {}).get(w, {}).get(k)
            out["limits"][w][k] = float(v) if isinstance(v, (int, float)) and v > 0 else None
    return out


def save_limits(data):
    clean = {"count_cache_reads": bool(data.get("count_cache_reads")), "limits": {}}
    for w in WINDOWS:
        clean["limits"][w] = {}
        for k in ("tokens", "cost"):
            try:
                v = float((data.get("limits") or {}).get(w, {}).get(k) or 0)
            except (TypeError, ValueError):
                v = 0
            clean["limits"][w][k] = v if v > 0 else None
    LIMITS_FILE.write_text(json.dumps(clean, indent=2))
    return load_limits()


def limit_tokens(r, count_cache_reads):
    return r["total"] if count_cache_reads else r["total"] - r["usage"]["cache_read"]


def _window_start(window, now):
    if window == "5h":
        return now - timedelta(hours=5)
    if window == "7d":
        return now - timedelta(days=7)
    local = now.astimezone()
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _limit_status(reqs, cfg):
    now = datetime.now(timezone.utc)
    out = []
    for w, label in WINDOWS.items():
        start = _window_start(w, now).timestamp()
        inside = [r for r in reqs if _ts(r) >= start]
        tokens = sum(limit_tokens(r, cfg["count_cache_reads"]) for r in inside)
        cost = sum(r["cost"] or 0 for r in inside)
        lim = cfg["limits"][w]
        if w == "month":
            local = now.astimezone()
            nxt = (local.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            resets = nxt.isoformat()
        else:
            # Rolling window: usage frees up as the oldest request ages out.
            span = timedelta(hours=5) if w == "5h" else timedelta(days=7)
            resets = (_local(inside[0]["timestamp"]) + span).isoformat() if inside else None
        out.append({
            "window": w, "label": label, "requests": len(inside),
            "tokens": tokens, "cost": cost,
            "token_limit": lim["tokens"], "cost_limit": lim["cost"],
            "tokens_left": None if lim["tokens"] is None else max(0, lim["tokens"] - tokens),
            "cost_left": None if lim["cost"] is None else max(0.0, lim["cost"] - cost),
            "resets": resets,
        })
    return out


def _projects_overview(reqs):
    rows = {}
    total_cost = sum(r["cost"] or 0 for r in reqs) or 0
    for r in reqs:
        p = rows.setdefault(r["project"], {**_blank(), "project": r["project"], "sessions": set(),
                                           "models": defaultdict(float), "tool_calls": defaultdict(int),
                                           "first": r["timestamp"], "last": r["timestamp"], "max_context": 0})
        _add(p, r)
        p["sessions"].add(r["session"])
        p["models"][r["model"]] += r["cost"] or 0
        for t in r["tools"]:
            p["tool_calls"][t] += 1
        p["last"] = r["timestamp"] or p["last"]
        p["max_context"] = max(p["max_context"], r["context"])
    out = []
    for p in rows.values():
        prompt = p["input"] + p["cache_write"] + p["cache_read"]
        n = len(p.pop("sessions"))
        models, tools = p.pop("models"), p.pop("tool_calls")
        out.append({**p, "sessions": n,
                    "share": _pct(p["cost"], total_cost),
                    "cache_hit_rate": _pct(p["cache_read"], prompt),
                    "avg_context": prompt / p["requests"] if p["requests"] else 0,
                    "cost_per_session": p["cost"] / n if n else 0,
                    "top_model": max(models, key=models.get) if models else None,
                    "top_tool": max(tools, key=tools.get) if tools else None})
    out.sort(key=lambda x: x["cost"], reverse=True)
    return out


def analyze(logs_dir=None, days=None, project=None):
    all_reqs = load_requests(logs_dir)
    cfg = load_limits()

    lifetime = _blank()
    for r in all_reqs:
        _add(lifetime, r)
    lifetime.update({
        "limit_tokens": sum(limit_tokens(r, cfg["count_cache_reads"]) for r in all_reqs),
        "sessions": len({r["session"] for r in all_reqs}),
        "projects": len({r["project"] for r in all_reqs}),
        "first": all_reqs[0]["timestamp"] if all_reqs else None,
    })

    reqs = all_reqs
    if days:
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        reqs = [r for r in reqs if _ts(r) >= cutoff]
    projects = _projects_overview(reqs)
    if project:
        reqs = [r for r in reqs if r["project"] == project]

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

    tool_stats = defaultdict(lambda: {"calls": 0, "result_chars": 0, "errors": 0})
    for r in reqs:
        for name in r["tools"]:
            tool_stats[name]["calls"] += 1
        for name, chars, err in r["tool_results"]:
            tool_stats[name]["result_chars"] += chars
            tool_stats[name]["errors"] += err
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

    limit_windows = _limit_status(all_reqs, cfg)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "logs_dir": str(Path(logs_dir) if logs_dir else LOGS_DIR),
        "project": project,
        "summary": summary,
        "lifetime": lifetime,
        "limits": {"count_cache_reads": cfg["count_cache_reads"], "windows": limit_windows},
        "projects": projects,
        "by_day": [{"day": d, **b} for d, b in sorted(by_day.items())],
        "by_hour": [{"hour": h, **by_hour.get(h, _blank())} for h in range(24)],
        "by_model": sorted(({"model": k, **v} for k, v in by_model.items()), key=lambda x: x["cost"], reverse=True),
        "sessions": sessions[:50],
        "tools": tools,
        "top_requests": [{
            "timestamp": r["timestamp"], "session": r["session"], "model": r["model"],
            "context": r["context"], "output": r["usage"]["output"], "cost": r["cost"],
            "tools": r["tools"], "subagent": r["subagent"]} for r in top],
        "insights": _limit_insights(limit_windows) + _insights(summary, sessions, tools, by_day, by_model),
    }


def _limit_insights(windows):
    out = []
    for w in windows:
        for used, limit, unit in ((w["tokens"], w["token_limit"], "token"), (w["cost"], w["cost_limit"], "cost")):
            if not limit:
                continue
            p = _pct(used, limit)
            if p >= 75:
                shown = f"${used:.2f} of ${limit:.2f}" if unit == "cost" else f"{_fmt(used)} of {_fmt(limit)} tokens"
                out.append({"level": "critical" if p >= 90 else "warning",
                            "text": f"{w['label']}: {p:.0f}% of your {unit} limit used ({shown})."})
    return out


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
