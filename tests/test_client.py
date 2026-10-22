import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from hl_mcp.api import HyperliquidClient
from hl_mcp.api.constants import BASE_URLS

from .conftest import ADDRESS, load_fixture

INFO_URL = f"{BASE_URLS['mainnet']}/info"


async def test_meta(info_mock, client):
    meta = await client.meta()
    assert meta.universe[0].name == "BTC"
    assert meta.universe[0].szDecimals == 5
    assert any(a.isDelisted for a in meta.universe)
    table_id, table = meta.marginTables[0]
    assert isinstance(table_id, int)
    assert table.marginTiers[0].lowerBound == Decimal("0")


async def test_meta_and_asset_ctxs(info_mock, client):
    meta, ctxs = await client.meta_and_asset_ctxs()
    assert len(meta.universe) == len(ctxs)
    btc = ctxs[0]
    raw = load_fixture("meta_and_asset_ctxs")[1][0]
    assert btc.markPx == Decimal(raw["markPx"])
    assert btc.funding == Decimal(raw["funding"])
    # delisted markets come back with null mid/premium/impact prices
    assert any(c.midPx is None and c.impactPxs is None for c in ctxs)


async def test_all_mids(info_mock, client):
    mids = await client.all_mids()
    assert mids["BTC"] == Decimal(load_fixture("all_mids")["BTC"])


async def test_l2_book(info_mock, client):
    book = await client.l2_book("BTC")
    bids, asks = book.levels
    assert book.coin == "BTC"
    assert book.time.tzinfo is not None
    assert bids[0].px < asks[0].px
    assert all(isinstance(lv.n, int) for lv in bids + asks)


async def test_clearinghouse_state(info_mock, client):
    state = await client.clearinghouse_state(ADDRESS)
    raw = load_fixture("clearinghouse_state")
    assert state.marginSummary.accountValue == Decimal(
        raw["marginSummary"]["accountValue"]
    )
    assert len(state.assetPositions) == len(raw["assetPositions"])
    pos = state.assetPositions[0].position
    assert pos.szi == Decimal(raw["assetPositions"][0]["position"]["szi"])
    assert any(ap.position.liquidationPx is None for ap in state.assetPositions)
    assert any(ap.position.liquidationPx is not None for ap in state.assetPositions)


async def test_user_fills(info_mock, client):
    fills = await client.user_fills(ADDRESS)
    assert fills[0].side in ("A", "B")
    assert {"Long > Short", "Short > Long"} <= {f.dir for f in fills}
    assert isinstance(fills[0].closedPnl, Decimal)


async def test_user_fills_by_time(info_mock, client):
    fills = await client.user_fills_by_time(ADDRESS, start_time=0)
    times = [f.time for f in fills]
    assert times == sorted(times)


async def test_user_funding(info_mock, client):
    events = await client.user_funding(ADDRESS, start_time=0)
    raw = load_fixture("user_funding")[0]
    assert events[0].delta.usdc == Decimal(raw["delta"]["usdc"])
    assert events[0].time == datetime.fromtimestamp(raw["time"] / 1000, UTC)


async def test_funding_history(info_mock, client):
    hist = await client.funding_history("BTC", start_time=0)
    assert {h.coin for h in hist} == {"BTC"}


async def test_candle_snapshot(info_mock, client):
    candles = await client.candle_snapshot("BTC", "1h", 0, 1)
    c = candles[0]
    assert c.s == "BTC" and c.i == "1h"
    assert c.l <= c.o <= c.h and c.l <= c.c <= c.h
    assert c.T > c.t


async def test_candle_snapshot_prefixes_dex(info_mock, client):
    route, _ = info_mock
    await client.candle_snapshot("FOO", "1h", 0, 1, dex="xyz")
    body = json.loads(route.calls.last.request.content)
    assert body["req"]["coin"] == "xyz:FOO"


async def test_none_fields_are_dropped(info_mock, client):
    route, _ = info_mock
    await client.meta()
    assert json.loads(route.calls.last.request.content) == {"type": "meta"}


def test_network_picks_base_url():
    assert str(HyperliquidClient("testnet").http.base_url).startswith(
        BASE_URLS["testnet"]
    )
    assert str(HyperliquidClient().http.base_url).startswith(BASE_URLS["mainnet"])


@respx.mock
async def test_retries_on_429_then_succeeds(client):
    route = respx.post(INFO_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, json={"BTC": "1"}),
        ]
    )
    assert await client.all_mids() == {"BTC": Decimal("1")}
    assert route.call_count == 3


@respx.mock
async def test_gives_up_after_max_retries():
    route = respx.post(INFO_URL).mock(return_value=httpx.Response(500))
    async with HyperliquidClient(max_retries=2) as c:
        with pytest.raises(httpx.HTTPStatusError):
            await c.all_mids()
    assert route.call_count == 3


@respx.mock
async def test_does_not_retry_client_errors(client):
    route = respx.post(INFO_URL).mock(return_value=httpx.Response(422))
    with pytest.raises(httpx.HTTPStatusError):
        await client.all_mids()
    assert route.call_count == 1


@respx.mock
async def test_retries_transport_errors(client):
    route = respx.post(INFO_URL).mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={})]
    )
    assert await client.all_mids() == {}
    assert route.call_count == 2
