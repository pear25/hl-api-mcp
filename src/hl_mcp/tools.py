"""Tool implementations shared by the MCP server and (later) the agent.

Each tool takes a HyperliquidClient and returns compact, labelled text meant
for an LLM to read. Expected failures raise HLToolError with a short message.

Sign convention for funding everywhere: positive = received, negative = paid.
"""

import difflib
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Hashable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from .api.hl_client import HyperliquidClient
from .api.models import AssetCtx, AssetMeta

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

MAX_BOOK_DEPTH = 20  # l2Book returns at most 20 levels per side
MAX_FILLS_LIMIT = 200
MAX_POSITIONS_LIMIT = 100
FILLS_PAGE_SIZE = 2000  # userFillsByTime cap per response
FUNDING_PAGE_SIZE = 500  # userFunding cap per response
MAX_PAGES = 10
HOURS_PER_YEAR = 24 * 365


class HLToolError(Exception):
    """An anticipated failure whose message is safe to show the model."""


# --- formatting ---


def _num(d: Decimal) -> str:
    return f"{d.normalize():,f}"


def _usd(d: Decimal) -> str:
    sign = "-" if d < 0 else ""
    return f"{sign}${abs(d):,.2f}"


def _signed_usd(d: Decimal) -> str:
    return f"+{_usd(d)}" if d > 0 else _usd(d)


def _pct(d: Decimal, places: int = 2) -> str:
    return f"{d * 100:.{places}f}%"


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%SZ")


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _now_ms() -> int:
    return int(time.time() * 1000)


# --- validation ---


def validate_address(address: str | None, default: str | None = None) -> str:
    address = (address or default or "").strip()
    if not address:
        raise HLToolError(
            "no address given and HL_DEFAULT_ADDRESS is not set; "
            "pass a 0x-prefixed 40-hex-char wallet address"
        )
    if not ADDRESS_RE.match(address):
        raise HLToolError(
            f"invalid address {address!r}; expected 0x followed by 40 hex chars"
        )
    return address.lower()


async def _resolve_coin(
    client: HyperliquidClient, coin: str
) -> tuple[AssetMeta, AssetCtx]:
    meta, ctxs = await client.meta_and_asset_ctxs()
    by_name = {
        a.name.upper(): (a, ctx) for a, ctx in zip(meta.universe, ctxs, strict=True)
    }
    key = coin.strip().upper()
    if key in by_name:
        return by_name[key]
    live = [a.name for a in meta.universe if not a.isDelisted]
    close = difflib.get_close_matches(key, [n.upper() for n in live], n=3)
    hint = f"; did you mean {', '.join(close)}?" if close else ""
    raise HLToolError(f"unknown coin {coin!r}{hint}")


# --- pagination ---


class _Timed(Protocol):
    time: datetime


async def _paginate[TT: _Timed](
    fetch: Callable[[int], Awaitable[list[TT]]],
    start_ms: int,
    page_size: int,
    key: Callable[[TT], Hashable],
) -> tuple[list[TT], bool]:
    """Walk a time-ranged endpoint forward from start_ms.

    Each page restarts at the last timestamp seen (not +1ms) since many rows can
    share a timestamp; duplicates are dropped by key. Returns (rows, truncated).
    """
    seen: dict[Hashable, TT] = {}
    for _ in range(MAX_PAGES):
        page = await fetch(start_ms)
        new = [r for r in page if key(r) not in seen]
        seen.update((key(r), r) for r in new)
        if len(page) < page_size or not new:
            return list(seen.values()), False
        start_ms = max(_ms(r.time) for r in page)
    return list(seen.values()), True


# --- tools ---


async def get_market_snapshot(client: HyperliquidClient, coin: str) -> str:
    asset, ctx = await _resolve_coin(client, coin)
    change = (
        (ctx.markPx - ctx.prevDayPx) / ctx.prevDayPx if ctx.prevDayPx else Decimal(0)
    )
    lines = [
        f"{asset.name} perp{' (DELISTED)' if asset.isDelisted else ''}",
        f"mark: {_num(ctx.markPx)} USD | oracle: {_num(ctx.oraclePx)} USD"
        + (f" | mid: {_num(ctx.midPx)} USD" if ctx.midPx is not None else ""),
        f"24h change: {_pct(change)} (prev day px {_num(ctx.prevDayPx)})",
        f"funding (hourly): {_pct(ctx.funding, 4)} | annualised: "
        f"{_pct(ctx.funding * HOURS_PER_YEAR)} (positive = longs pay shorts)",
        f"open interest: {_num(ctx.openInterest)} {asset.name} "
        f"({_usd(ctx.openInterest * ctx.markPx)})",
        f"24h volume: {_usd(ctx.dayNtlVlm)}",
        f"max leverage: {asset.maxLeverage}x",
    ]
    if ctx.premium is not None:
        lines.append(f"premium: {_pct(ctx.premium, 4)}")
    return "\n".join(lines)


async def get_order_book(client: HyperliquidClient, coin: str, depth: int = 10) -> str:
    asset, _ = await _resolve_coin(client, coin)
    depth = max(1, min(depth, MAX_BOOK_DEPTH))
    book = await client.l2_book(asset.name)
    bids, asks = book.levels
    lines = [f"{asset.name} order book at {_ts(book.time)} (px USD, sz {asset.name})"]
    if bids and asks:
        best_bid, best_ask = bids[0].px, asks[0].px
        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid
        lines.append(
            f"mid: {_num(mid)} | spread: {_num(spread)} "
            f"({spread / mid * 10000:.2f} bps)"
        )
    for label, side in (("asks", asks), ("bids", bids)):
        shown = side[:depth]
        lines.append(f"{label} (showing {len(shown)} of {len(side)} levels):")
        lines += [f"  {_num(lv.px)} x {_num(lv.sz)} ({lv.n} orders)" for lv in shown]
    return "\n".join(lines)


async def get_account_summary(client: HyperliquidClient, address: str) -> str:
    state = await client.clearinghouse_state(address)
    m = state.marginSummary
    leverage = m.totalNtlPos / m.accountValue if m.accountValue else Decimal(0)
    usage = m.totalMarginUsed / m.accountValue if m.accountValue else Decimal(0)
    return "\n".join(
        [
            f"account {address} at {_ts(state.time)}",
            f"account value: {_usd(m.accountValue)}",
            f"total position notional: {_usd(m.totalNtlPos)}",
            f"effective leverage: {leverage:.2f}x",
            f"margin used: {_usd(m.totalMarginUsed)} ({_pct(usage)} of account)",
            f"cross maintenance margin: {_usd(state.crossMaintenanceMarginUsed)}",
            f"withdrawable: {_usd(state.withdrawable)}",
            f"open positions: {len(state.assetPositions)}",
        ]
    )


async def get_positions(
    client: HyperliquidClient, address: str, limit: int = 20
) -> str:
    state = await client.clearinghouse_state(address)
    positions = sorted(
        (ap.position for ap in state.assetPositions),
        key=lambda p: p.positionValue,
        reverse=True,
    )
    if not positions:
        return f"account {address} has no open positions"
    limit = max(1, min(limit, MAX_POSITIONS_LIMIT))
    shown = positions[:limit]
    total_upnl = sum((p.unrealizedPnl for p in positions), Decimal(0))
    lines = [
        f"positions for {address} at {_ts(state.time)} "
        f"(showing {len(shown)} of {len(positions)}, largest notional first)",
        f"total unrealised PnL (all positions): {_signed_usd(total_upnl)}",
    ]
    for p in shown:
        side = "LONG" if p.szi > 0 else "SHORT"
        liq = _num(p.liquidationPx) if p.liquidationPx is not None else "n/a"
        lines.append(
            f"- {p.coin} {side} {_num(abs(p.szi))} | notional {_usd(p.positionValue)}"
            f" | entry {_num(p.entryPx)} | uPnL {_signed_usd(p.unrealizedPnl)}"
            f" (ROE {_pct(p.returnOnEquity)}) | {p.leverage.type} {p.leverage.value}x"
            f" | liq {liq} | margin {_usd(p.marginUsed)}"
            # cumFunding is reported as paid-positive; flip to received-positive
            f" | funding since open {_signed_usd(-p.cumFunding.sinceOpen)}"
        )
    return "\n".join(lines)


async def get_recent_fills(
    client: HyperliquidClient,
    address: str,
    since_hours: float = 24,
    limit: int = 50,
) -> str:
    if since_hours <= 0:
        raise HLToolError("since_hours must be positive")
    limit = max(1, min(limit, MAX_FILLS_LIMIT))
    start_ms = _now_ms() - int(since_hours * 3_600_000)
    fills, truncated = await _paginate(
        lambda s: client.user_fills_by_time(address, s, aggregate_by_time=True),
        start_ms,
        FILLS_PAGE_SIZE,
        key=lambda f: (f.tid, f.oid),
    )
    if not fills:
        return f"no fills for {address} in the last {since_hours:g}h"
    fills.sort(key=lambda f: f.time, reverse=True)
    shown = fills[:limit]
    realised = sum((f.closedPnl for f in fills), Decimal(0))
    fees = sum((f.fee for f in fills), Decimal(0))
    lines = [
        f"fills for {address} in the last {since_hours:g}h "
        f"(showing {len(shown)} of {len(fills)}, newest first)",
        f"window totals: closed PnL {_signed_usd(realised)} | fees {_usd(fees)}",
    ]
    if truncated:
        lines.append(
            f"note: page cap reached; only fills up to {_ts(fills[0].time)} included"
        )
    oldest = fills[-1].time
    if _ms(oldest) - start_ms > 3_600_000 and len(fills) >= FILLS_PAGE_SIZE:
        lines.append(
            f"note: API only keeps the 10,000 most recent fills; "
            f"coverage starts at {_ts(oldest)}"
        )
    for f in shown:
        side = "BUY" if f.side == "B" else "SELL"
        lines.append(
            f"- {_ts(f.time)} {f.coin} {side} {_num(f.sz)} @ {_num(f.px)}"
            f" ({f.dir}) | closed PnL {_signed_usd(f.closedPnl)}"
            f" | fee {_num(f.fee)} {f.feeToken}"
        )
    return "\n".join(lines)


async def get_funding_payments(
    client: HyperliquidClient,
    address: str,
    since_hours: float = 168,
    top: int = 20,
) -> str:
    if since_hours <= 0:
        raise HLToolError("since_hours must be positive")
    start_ms = _now_ms() - int(since_hours * 3_600_000)
    events, truncated = await _paginate(
        lambda s: client.user_funding(address, s),
        start_ms,
        FUNDING_PAGE_SIZE,
        key=lambda e: (_ms(e.time), e.delta.coin),
    )
    if not events:
        return f"no funding payments for {address} in the last {since_hours:g}h"
    by_coin: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    for e in events:
        by_coin[e.delta.coin] += e.delta.usdc
        counts[e.delta.coin] += 1
    net = sum(by_coin.values(), Decimal(0))
    received = sum((v for v in by_coin.values() if v > 0), Decimal(0))
    paid = sum((v for v in by_coin.values() if v < 0), Decimal(0))
    ranked = sorted(by_coin.items(), key=lambda kv: abs(kv[1]), reverse=True)
    shown = ranked[: max(1, top)]
    lines = [
        f"funding for {address} in the last {since_hours:g}h "
        f"({len(events)} payments; positive = received, negative = paid)",
        f"net: {_signed_usd(net)} | received: {_signed_usd(received)} "
        f"| paid: {_signed_usd(paid)}",
        f"by coin (showing {len(shown)} of {len(ranked)}, largest absolute first):",
    ]
    lines += [
        f"  {coin}: {_signed_usd(total)} over {counts[coin]} payments"
        for coin, total in shown
    ]
    if truncated:
        last = max(e.time for e in events)
        lines.append(
            f"note: page cap reached; totals only cover payments up to {_ts(last)}"
        )
    return "\n".join(lines)
