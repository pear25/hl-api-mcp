import json
from pathlib import Path

import httpx
import pytest
import respx

from hl_mcp.api import HyperliquidClient
from hl_mcp.api.constants import BASE_URLS

FIXTURES = Path(__file__).parent / "fixtures"

# info request type -> recorded response file
FIXTURE_FOR_TYPE = {
    "meta": "meta",
    "metaAndAssetCtxs": "meta_and_asset_ctxs",
    "allMids": "all_mids",
    "l2Book": "l2_book",
    "clearinghouseState": "clearinghouse_state",
    "userFills": "user_fills",
    "userFillsByTime": "user_fills_by_time",
    "userFunding": "user_funding",
    "fundingHistory": "funding_history",
    "candleSnapshot": "candle_snapshot",
}

ADDRESS = "0x010461c14e146ac35fe42271bdc1134ee31c703a"


def load_fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def info_mock():
    """Route POST /info to the recorded fixture for the request's type.

    Yields (route, overrides); set overrides[type] to a list or callable to
    replace a fixture for one test.
    """
    overrides: dict = {}

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        kind = body["type"]
        if kind in overrides:
            o = overrides[kind]
            return httpx.Response(200, json=o(body) if callable(o) else o)
        return httpx.Response(200, json=load_fixture(FIXTURE_FOR_TYPE[kind]))

    with respx.mock(assert_all_called=False) as router:
        route = router.post(f"{BASE_URLS['mainnet']}/info").mock(side_effect=respond)
        yield route, overrides


@pytest.fixture
async def client():
    async with HyperliquidClient("mainnet") as c:
        yield c


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr("hl_mcp.api.hl_client.asyncio.sleep", instant)
