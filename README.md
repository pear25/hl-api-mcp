# hl-mcp

A **read-only** MCP server for Hyperliquid's public info API, plus a Claude-powered trading copilot that answers questions about a trading book and sends a daily brief.

> **Status:** early development (M0: repo and CI skeleton). Most features below are planned, not built yet. See [the build plan](Hyperliquid_MCP_Agent_Build_Plan.md).

## Security model

- **Read-only.** It only calls `POST /info`. No code path reaches the exchange endpoint.
- **No private keys** anywhere in the codebase.
- **No trading.** The agent can flag risks but never places or cancels orders, and never recommends trades.

## What it does

**MCP tools** (for Claude Code / Claude Desktop):

| Tool | Returns |
| --- | --- |
| `get_market_snapshot(coin)` | Mark price, funding, open interest |
| `get_order_book(coin, depth)` | Top-of-book levels |
| `get_account_summary(address)` | Account value, margin |
| `get_positions(address)` | Open positions |
| `get_recent_fills(address, since_hours, limit)` | Recent trades |
| `get_funding_payments(address, since_hours)` | Funding paid or received |
| `pnl_summary(address, window)` | Realised and unrealised PnL, fees, funding |
| `risk_snapshot(address)` | Exposure, leverage, liquidation distance |

**Daily brief agent:** a Claude API tool-use loop that builds a schema-validated brief (PnL, top positions, risk flags, funding) and sends it to Telegram. All maths runs in Python, and the model only quotes tool results.

## Quickstart

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> && cd hl-mcp
uv sync
cp .env.example .env   # then fill in values
```

Run lint and tests:

```bash
uv run ruff check
uv run pytest
```

Once the server is built (M2), register it with Claude Code:

```bash
claude mcp add hyperliquid -- uv run hl-mcp
```

## Stack

Python 3.12 · uv · httpx (async) · Pydantic v2 (Decimal for all numbers) · FastMCP (stdio) · Anthropic SDK · pytest + respx on recorded fixtures

## Roadmap

| # | Milestone | Status |
| --- | --- | --- |
| M0 | Repo and CI skeleton | In progress |
| M1 | Typed Hyperliquid client | Planned |
| M2 | MCP server v1 | Planned |
| M3 | Deterministic analytics (PnL and risk) | Planned |
| M4 | Guardrails and ops | Planned |
| M5 | Claude API agent and Telegram brief | Planned |
| M6 | Eval suite | Planned |
| M7 | Ship v0.1.0 | Planned |

## Evals

Coming in M6: numeric accuracy, tool-selection accuracy, schema validity, and cost and latency per run.
