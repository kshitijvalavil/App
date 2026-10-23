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
