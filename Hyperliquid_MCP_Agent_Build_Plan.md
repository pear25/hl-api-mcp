## Hyperliquid MCP Server + Trading Copilot Agent

Build plan · Python · read-only · Claude API

## Objective

Ship a read-only MCP server in Python over Hyperliquid's public info API, then a Claude-API agent that uses it to answer natural-language questions about a trading book and produce a daily book brief, backed by deterministic analytics and an eval suite.

## Definition of done

- MCP server works in Claude Code / Claude Desktop against mainnet data.

- Agent produces a schema-validated daily brief and delivers it to Telegram.

- Eval table in README with real numbers (numeric accuracy, tool-selection accuracy, cost and latency per run).

- Tests and CI green on recorded fixtures.

## Non-goals

- No order placement, no exchange endpoints, no private keys anywhere in the codebase.

- No web front-end.

- No model training or fine-tuning.

## Stack and key decisions

| Layer | Choice | Tradeoff |
| --- | --- | --- |
| Runtime | Python 3.12, uv, ruff, pytest | Matches your toolchain. |
| Hyperliquid access | Direct POST /info with httpx (async) + your own Pydantic models | More work than hyperliquid-python-sdk, but fewer deps, typed outputs you control, and shows you understand the API. SDK is fine if time-boxed. |
| MCP | Official mcp Python SDK (FastMCP), stdio transport | stdio is simplest for Claude Code/Desktop; add streamable HTTP only if you deploy remotely. |
| Agent | anthropic SDK with a hand-written tool-use loop | Hand-written loop shows you understand tool use; Claude Agent SDK is faster to wire up but hides the mechanics. Pick one, mention the other. |
| Numbers | Decimal everywhere; API returns numeric strings| Avoids float drift in PnL; small perf cost, irrelevant here. |
| Testing | pytest + respx (httpx mocking) on recorded JSON fixtures | Deterministic CI with no network; refresh fixtures manually. |

## Milestones

Estimates assume focused ev(s)

| # | Milestone | Est. | Relevant output |
| --- | --- | --- | --- |
| M0 | Repo + CI skeleton | 0.5d | Green CI |
| M1 | Typed Hyperliquid client | 1d | Tested client on fixtures |
| M2 | MCP server v1 | 1d | Working in Claude Code |
| M3 | Deterministic analytics | 1d | PnL / risk computed in Python |
| M4 | Guardrails + ops | 0.5d | Security model in README |
| M5 | Claude-API agent + brief | 1.5d | Daily brief to Telegram |
| M6 | Eval suite | 1.5d | Eval table with real numbers |


| M7 | Ship + package | 0.5d | v0.1 tag, demo GIF, bullets |
| --- | --- | --- | --- |

## M0 · Repo and CI skeleton (0.5 day)

Goal: A clean, credible repo from commit one.

- uv init; src layout (src/hl_mcp/), ruff, pytest, MIT licence.

- GitHub Actions: lint + test on push.

- README skeleton: objective, security model (read-only), quickstart placeholder.

- .env.example with HL_NETWORK=mainnet|testnet and default address; never commit real config.

Done when: CI passes on an empty test; README states the read-only promise up front.

## M1 · Typed Hyperliquid client (1 day)

Goal: One async client that wraps every info call you need, with typed outputs.

- Base URLs: https://api.hyperliquid.xyz/info (mainnet) and the testnet equivalent; all calls are POST with a JSON body like {"type": "l2Book", "coin": "BTC"}.

- Wrap these info types: meta / metaAndAssetCtxs (markets, mark price, funding, OI), allMids, l2Book, clearinghouseState (positions, margin, account value), userFills / userFillsByTime, userFunding, fundingHistory, candleSnapshot.

- Pydantic v2 models parsing numeric strings to Decimal. Verify every field name against real responses; don't trust memory or blog posts.

- Timeouts, retry with backoff on 429/5xx, one shared httpx.AsyncClient.

- Record real responses once into tests/fixtures/*.json; unit-test parsing against them with respx. Done when: Every wrapped call has a passing fixture test; the client can be pointed at mainnet or testnet by config.

## M2 · MCP server v1 (1 day)

Goal: Claude can answer questions about any address's book through your tools.

- Tools (FastMCP decorators, clear docstrings, typed args): get_market_snapshot(coin), get_order_book(coin, depth=10), get_account_summary(address), get_positions(address), get_recent_fills(address, since_hours=24, limit=50), get_funding_payments(address, since_hours=168).

- Design outputs for an LLM, not a UI: compact, labelled, units explicit, truncated with a 'showing N of M' note. Never dump 2,000 raw fills into context.

- Errors come back as short readable messages ('unknown coin XYZ; did you mean...'), not stack traces.

- Register locally: claude mcp add hyperliquid -- uv run hl-mcp (check current CLI syntax). Done when: In Claude Code you can ask 'What's my BTC exposure, leverage and funding paid this week?' and get a correct answer you've checked by hand.

## M3 · Deterministic analytics layer (1 day)

Goal: All maths happens in Python; the model only reads results.

- pnl_summary(address, window): realised PnL from fills' closed-PnL field, fees, funding paid/received, unrealised PnL from current positions, net total.

- risk_snapshot(address): exposure by coin (notional and % of account), effective leverage, margin usage, distance to liquidation price per position, funding drag annualised.

- Expose both as MCP tools; the agent prompt tells the model to quote these figures rather than compute its own.

- Hand-computed unit tests for each metric, including edge cases: flipped positions, partial closes, zero positions. Done when: Metrics match a manual spreadsheet check on at least two real addresses.

## M4 · Guardrails and ops (0.5 day)

Goal: A security story you can tell a trading desk in 30 seconds.

- Allowlist of info types inside the client; there is no code path to the exchange endpoint.

- Validate addresses (0x + 40 hex) and coins against meta before calling.

- Respect Hyperliquid's weight-based per-IP rate limits (check current docs); short TTL cache for meta and mids.

- Structured log line per tool call: tool, args, latency, response size.

- README 'Security model' section: read-only, no keys, what the agent can and cannot do.

Done when: You can explain why an agent using this server cannot place or cancel an order.

## M5 · Claude-API agent and daily brief (1.5 days)

Goal: An agent that turns raw book data into a decision-ready brief, on a schedule.


- Tool-use loop with the anthropic SDK, reusing the same tool functions (import them directly or connect via MCP).

- Output schema (Pydantic): headline, PnL breakdown, top positions, risk flags, notable fills, funding commentary. Validate; retry once on schema failure.

- System prompt rules: every number must come from a tool result; say 'no data' rather than guess; flag, don't recommend trades.

- Render to Markdown and send via a Telegram bot; schedule with cron or a GitHub Actions workflow.

- Log tokens, cost and latency per run.

Done when: A brief arrives on Telegram daily for a chosen address, and every number in it traces back to a tool call.

## M6 · Eval suite (1.5 days)

Goal: Hard numbers proving the agent is accurate, not just fluent.

- Golden set: recorded fixtures for 10–20 historical windows across a few public addresses (vaults and your own wallet are fine).

- Numeric fidelity: every number in the brief's structured fields must match the M3 computed value within tolerance; report % exact.

- Tool selection: 20–30 natural-language questions with expected tool calls and answers; report pass rate.

- Schema validity rate, cost and latency per run; optionally compare two models.

- Run evals on fixtures in CI so a prompt change that breaks accuracy fails the build.

Done when: README has an eval table with real numbers, and CI runs it.

## M7 · Ship and package (0.5 day)

Goal: Make it legible to a recruiter in 60 seconds.

- README: one-paragraph pitch, architecture diagram (Mermaid), demo GIF of Claude Code using the tools, eval table, quickstart.

- Tag v0.1.0; optional PyPI publish so uvx hl-mcp works.

Done when: A stranger can install it and query a book in under five minutes.

## Stretch goals (only after M7)

- WebSocket subscriptions for live alerts (fills, liquidation-distance breaches) pushed to Telegram.

- HIP-3 builder-deployed perp dexes via the dex parameter; ties directly to your NVNM work.

- Plug the MCP server into your portfolio app so its reports cover crypto perps too.

- Multi-address book aggregation (desk view across sub-accounts).

## Risks and how to handle them

- Field names or API behaviour differ from what you expect: fixtures-first; models are built from real responses.

- Scope creep into a dashboard: M0–M4 is the minimum shippable; resist UI work.

- Compliance: the tool is read-only and never trades, so it shouldn't touch your pre-approval obligations; still, demo against public addresses or testnet if in doubt.

- Rate limits during evals: evals run on recorded fixtures, never live.

## Interview talking points this unlocks

- Why read-only, and how you'd add write tools safely (human approval, limits, kill switch).

- Why the LLM never does arithmetic, and how the evals prove it.

- How you shaped tool outputs to protect context (the same lean-context instinct behind choosing OpenSpec over GSD).

- Hand-written tool loop vs Agent SDK vs MCP: when you'd use each on a trading desk.
