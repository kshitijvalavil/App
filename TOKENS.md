# Token usage dashboard

Open `/tokens` after starting the app (`python MyAPP.py`, then http://localhost:5000/tokens).

It reads Claude Code session transcripts (`~/.claude/projects/**/*.jsonl` by default,
override with `CLAUDE_LOGS_DIR`) and shows:

- Totals: tokens, estimated cost, savings from prompt caching, cache hit rate, context size
- Tokens per day split into input / cache write / cache read / output
- Cost by token type, by model, by hour of day
- Sessions, projects, tools (how much text each tool feeds back into context), most expensive requests
- Generated insights with concrete suggestions

**Refresh** re-reads the logs; **Auto-refresh** polls every 30s / 1m / 5m. Raw JSON is at `/api/tokens?days=7`.

Costs are estimates from list prices in `token_usage.py` (`PRICING`); edit that table if your rates differ.

## Limits, lifetime & projects

- **Limits & what's left** — set token and/or $ limits per rolling window (last 5 hours, last 7 days, this month) via **Edit limits**. Each shows a meter with how much is left, % used, and when the window rolls off. Saved to `limits.json` (override path with `TOKEN_LIMITS_FILE`). Over 75% turns the meter amber, 90% red, and raises an alert in Insights. Cache reads are excluded from limit counts by default (toggle in the editor), since they bill at a fraction of input.
- **Lifetime** — all-time totals across every transcript, ignoring the date range.
- **Usage by project** — ranked share bar + table (sessions, tokens, cache hit, avg/peak context, top model & tool, $/session, share). Click any row, or use the **Project** filter, to scope the whole dashboard to one project.

Claude plans don't expose their usage caps as token numbers, so the limit amounts are yours to set.
