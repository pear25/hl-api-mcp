import json
from decimal import Decimal

import pytest

from hl_mcp import tools
from hl_mcp.tools import HLToolError

from .conftest import ADDRESS, load_fixture

T0 = 1_790_000_000_000  # ms; small ints would parse as seconds


def _funding_event(t: int, coin: str, usdc: str) -> dict:
    """t is an offset in ms from T0."""
    return {
        "time": T0 + t,
        "hash": "0x" + "0" * 64,
        "delta": {
            "type": "funding",
            "coin": coin,
            "usdc": usdc,
            "szi": "1.0",
            "fundingRate": "0.0000125",
            "nSamples": None,
        },
    }


# --- validation ---


def test_validate_address_normalises_case():
    assert tools.validate_address(ADDRESS.upper().replace("0X", "0x")) == ADDRESS


def test_validate_address_falls_back_to_default():
    assert tools.validate_address(None, ADDRESS) == ADDRESS


@pytest.mark.parametrize("bad", ["0x123", "abc", "0x" + "g" * 40, ADDRESS + "0"])
def test_validate_address_rejects_bad_input(bad):
    with pytest.raises(HLToolError, match="invalid address"):
        tools.validate_address(bad)


def test_validate_address_requires_some_address():
    with pytest.raises(HLToolError, match="HL_DEFAULT_ADDRESS"):
        tools.validate_address(None, None)


# --- market ---


async def test_market_snapshot(info_mock, client):
    out = await tools.get_market_snapshot(client, "btc")
    raw = load_fixture("meta_and_asset_ctxs")[1][0]
    mark = Decimal(raw["markPx"])
    assert out.startswith("BTC perp")
    assert f"mark: {mark:,f}".rstrip("0").rstrip(".") in out
    assert "annualised" in out
    assert "max leverage: 40x" in out


async def test_market_snapshot_unknown_coin_suggests(info_mock, client):
    with pytest.raises(HLToolError, match=r"unknown coin 'BTX'; did you mean .*BTC"):
        await tools.get_market_snapshot(client, "BTX")


async def test_market_snapshot_flags_delisted(info_mock, client):
    out = await tools.get_market_snapshot(client, "MATIC")
    assert "DELISTED" in out


@pytest.mark.parametrize(
    "coin, dex", [("dram", "xyz"), ("xyz:DRAM", None), ("DRAM", "XYZ")]
)
async def test_market_snapshot_hip3_dex(info_mock, client, coin, dex):
    route, _ = info_mock
    out = await tools.get_market_snapshot(client, coin, dex)
    assert out.startswith("xyz:DRAM perp")
    raw = load_fixture("meta_and_asset_ctxs_xyz")[1][-1]
    assert f"mark: {Decimal(raw['markPx']).normalize():,f} USD" in out
    bodies = [json.loads(c.request.content) for c in route.calls]
    assert {"type": "metaAndAssetCtxs", "dex": "xyz"} in bodies


async def test_market_snapshot_unknown_dex_lists_available(info_mock, client):
    route, _ = info_mock
    with pytest.raises(HLToolError, match=r"unknown dex 'nope'; available: xyz, "):
        await tools.get_market_snapshot(client, "DRAM", "nope")
    kinds = [json.loads(c.request.content)["type"] for c in route.calls]
    assert "metaAndAssetCtxs" not in kinds


async def test_market_snapshot_unknown_coin_on_dex(info_mock, client):
    with pytest.raises(HLToolError, match=r"on dex 'xyz'; did you mean XYZ:DRAM"):
        await tools.get_market_snapshot(client, "DRAMM", "xyz")


async def test_market_snapshot_main_dex_miss_hints_at_dex(info_mock, client):
    with pytest.raises(HLToolError, match=r"pass its dex"):
        await tools.get_market_snapshot(client, "DRAM")


async def test_order_book_depth_and_spread(info_mock, client):
    out = await tools.get_order_book(client, "BTC", depth=3)
    assert "asks (showing 3 of 20 levels)" in out
    assert "bids (showing 3 of 20 levels)" in out
    assert "bps" in out


async def test_order_book_depth_is_clamped(info_mock, client):
    out = await tools.get_order_book(client, "BTC", depth=500)
    assert "showing 20 of 20" in out


# --- account ---


async def test_account_summary(info_mock, client):
    out = await tools.get_account_summary(client, ADDRESS)
    m = load_fixture("clearinghouse_state")["marginSummary"]
    av, ntl = Decimal(m["accountValue"]), Decimal(m["totalNtlPos"])
    assert f"account value: ${av:,.2f}" in out
    assert f"effective leverage: {ntl / av:.2f}x" in out
    assert "open positions: 177" in out


async def test_positions_sorted_and_truncated(info_mock, client):
    out = await tools.get_positions(client, ADDRESS, limit=5)
    assert "showing 5 of 177" in out
    rows = [line for line in out.splitlines() if line.startswith("- ")]
    assert len(rows) == 5
    notionals = [
        Decimal(r.split("notional $")[1].split(" ")[0].replace(",", "")) for r in rows
    ]
    assert notionals == sorted(notionals, reverse=True)


async def test_positions_flip_funding_sign(info_mock, client):
    raw = load_fixture("clearinghouse_state")["assetPositions"]
    top = max(raw, key=lambda a: Decimal(a["position"]["positionValue"]))["position"]
    out = await tools.get_positions(client, ADDRESS, limit=1)
    paid = Decimal(top["cumFunding"]["sinceOpen"])
    expected = f"-${paid:,.2f}" if paid > 0 else f"+${-paid:,.2f}"
    assert f"funding since open {expected}" in out


async def test_positions_empty(info_mock, client):
    _, overrides = info_mock
    state = load_fixture("clearinghouse_state")
    overrides["clearinghouseState"] = {**state, "assetPositions": []}
    out = await tools.get_positions(client, ADDRESS)
    assert "no open positions" in out


# --- fills ---


async def test_recent_fills_newest_first_with_totals(info_mock, client):
    out = await tools.get_recent_fills(client, ADDRESS, since_hours=24, limit=5)
    raw = load_fixture("user_fills_by_time")
    assert f"showing 5 of {len(raw)}" in out
    realised = sum(Decimal(f["closedPnl"]) for f in raw)
    sign = "+" if realised > 0 else ("-" if realised < 0 else "")
    assert f"closed PnL {sign}${abs(realised):,.2f}" in out
    stamps = [line[2:22] for line in out.splitlines() if line.startswith("- ")]
    assert stamps == sorted(stamps, reverse=True)


async def test_recent_fills_requests_aggregation(info_mock, client):
    route, _ = info_mock
    await tools.get_recent_fills(client, ADDRESS)
    body = json.loads(route.calls.last.request.content)
    assert body["aggregateByTime"] is True


async def test_recent_fills_empty(info_mock, client):
    _, overrides = info_mock
    overrides["userFillsByTime"] = []
    out = await tools.get_recent_fills(client, ADDRESS, since_hours=1)
    assert out == f"no fills for {ADDRESS} in the last 1h"


async def test_recent_fills_rejects_bad_window(client):
    with pytest.raises(HLToolError):
        await tools.get_recent_fills(client, ADDRESS, since_hours=0)


# --- funding ---


async def test_funding_totals(info_mock, client):
    out = await tools.get_funding_payments(client, ADDRESS, top=3)
    raw = load_fixture("user_funding")
    net = sum(Decimal(e["delta"]["usdc"]) for e in raw)
    sign = "+" if net > 0 else "-"
    assert f"net: {sign}${abs(net):,.2f}" in out
    assert f"({len(raw)} payments;" in out
    assert "showing 3 of" in out


async def test_funding_paginates_and_dedupes(info_mock, client, monkeypatch):
    monkeypatch.setattr(tools, "FUNDING_PAGE_SIZE", 3)
    monkeypatch.setattr(tools, "_now_ms", lambda: T0 + 168 * 3_600_000 + 1000)
    _, overrides = info_mock
    events = [
        _funding_event(1000, "BTC", "-1"),
        _funding_event(1000, "ETH", "2"),
        _funding_event(2000, "BTC", "-1"),
        _funding_event(2000, "ETH", "2"),
        _funding_event(3000, "BTC", "-1"),
    ]
    starts = []

    def page(body):
        starts.append(body["startTime"] - T0)
        rows = [e for e in events if e["time"] >= body["startTime"]]
        return rows[:3]

    overrides["userFunding"] = page
    out = await tools.get_funding_payments(client, ADDRESS)
    # restarts at the last seen timestamp so same-timestamp rows aren't skipped
    assert starts == [1000, 2000, 3000]
    assert "(5 payments;" in out
    assert "net: +$1.00" in out
    assert "BTC: -$3.00 over 3 payments" in out
    assert "page cap" not in out


async def test_funding_reports_truncation(info_mock, client, monkeypatch):
    monkeypatch.setattr(tools, "FUNDING_PAGE_SIZE", 1)
    monkeypatch.setattr(tools, "MAX_PAGES", 2)
    _, overrides = info_mock
    overrides["userFunding"] = lambda body: [
        _funding_event(body["startTime"] - T0 + 1000, "BTC", "-1")
    ]
    out = await tools.get_funding_payments(client, ADDRESS)
    assert "page cap reached" in out


async def test_funding_empty(info_mock, client):
    _, overrides = info_mock
    overrides["userFunding"] = []
    out = await tools.get_funding_payments(client, ADDRESS, since_hours=24)
    assert "no funding payments" in out
