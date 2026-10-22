# hl-mcp

A **read-only** MCP server for Hyperliquid's public info API, plus a Claude-powered trading copilot that answers questions about a trading book and sends a daily brief.

> **Status:** early development. M0–M2 are done: a typed Hyperliquid client and an MCP server with six read-only tools. Analytics, guardrails, the agent and evals are planned. See [the build plan](Hyperliquid_MCP_Agent_Build_Plan.md).

## Security model

- **Read-only.** It only calls `POST /info`. No code path reaches the exchange endpoint.
- **No private keys** anywhere in the codebase.
- **No trading.** The agent can flag risks but never places or cancels orders, and never recommends trades.

## What it does

**MCP tools** (for Claude Code / Claude Desktop):

| Tool | Returns | Status |
| --- | --- | --- |
| `get_market_snapshot(coin, dex=None)` | Mark/oracle price, 24h change, funding, open interest, volume; `dex` (or a `xyz:DRAM` coin) targets a HIP-3 dex | Built |
| `get_order_book(coin, depth=10)` | Top-of-book levels and spread | Built |
| `get_account_summary(address)` | Account value, notional, leverage, margin | Built |
| `get_positions(address, limit=20)` | Open positions, largest first | Built |
| `get_recent_fills(address, since_hours=24, limit=50)` | Recent trades with closed PnL and fees | Built |
| `get_funding_payments(address, since_hours=168)` | Funding paid or received, net and per coin | Built |
| `pnl_summary(address, window)` | Realised and unrealised PnL, fees, funding | M3 |
| `risk_snapshot(address)` | Exposure, leverage, liquidation distance | M3 |

`address` is optional on account tools and falls back to `HL_DEFAULT_ADDRESS`. Funding is always signed from the account's side: positive = received, negative = paid. Long outputs are truncated with a "showing N of M" note.

**Daily brief agent:** a Claude API tool-use loop that builds a schema-validated brief (PnL, top positions, risk flags, funding) and sends it to Telegram. All maths runs in Python, and the model only quotes tool results.

## Quickstart

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/pear25/hl-api-mcp.git && cd hl-api-mcp
uv sync
cp .env.example .env   # then fill in values
```

Run lint and tests:

```bash
uv run ruff check
uv run pytest
```

Register the server with Claude Code (run from anywhere; `--directory` points uv at the repo):

```bash
claude mcp add hyperliquid -- uv run --directory /path/to/hl-api-mcp hl-mcp
```

Then ask something like "What's the BTC funding rate and my largest positions?"

## Layout

```
src/hl_mcp/
  api/          typed async client for POST /info (models, retries, base URLs)
  tools.py      tool logic, returns compact text; reusable by the M5 agent
  server.py     MCPServer wiring, arg schemas, error mapping
  config.py     HL_NETWORK / HL_DEFAULT_ADDRESS from env or .env
tests/fixtures/ real mainnet responses recorded 2026-10-21
```

## Stack

Python 3.12 · uv · httpx (async) · Pydantic v2 (Decimal for all numbers) · MCP Python SDK v2 `MCPServer` (stdio) · Anthropic SDK · pytest + respx on recorded fixtures

## Roadmap

| # | Milestone | Status |
| --- | --- | --- |
| M0 | Repo and CI skeleton | Done |
| M1 | Typed Hyperliquid client | Done |
| M2 | MCP server v1 | Done |
| M3 | Deterministic analytics (PnL and risk) | Planned |
| M4 | Guardrails and ops | Planned |
| M5 | Claude API agent and Telegram brief | Planned |
| M6 | Eval suite | Planned |
| M7 | Ship v0.1.0 | Planned |

## Evals

Coming in M6: numeric accuracy, tool-selection accuracy, schema validity, and cost and latency per run.
