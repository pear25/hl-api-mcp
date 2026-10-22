import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from hl_mcp import server
from hl_mcp.tools import HLToolError

EXPECTED_TOOLS = {
    "get_market_snapshot",
    "get_order_book",
    "get_account_summary",
    "get_positions",
    "get_recent_fills",
    "get_funding_payments",
}


async def test_registers_expected_tools():
    listed = await server.mcp.list_tools()
    assert {t.name for t in listed} == EXPECTED_TOOLS
    for t in listed:
        assert t.annotations.read_only_hint is True
        assert t.description
        # ctx is injected by the server, never exposed to the model
        assert "ctx" not in t.input_schema["properties"]


def _raising(exc):
    @server._readable_errors
    async def fn() -> str:
        raise exc

    return fn


@pytest.mark.parametrize(
    "exc, message",
    [
        (HLToolError("unknown coin 'X'"), "unknown coin 'X'"),
        (
            httpx.HTTPStatusError(
                "x",
                request=httpx.Request("POST", "http://x"),
                response=httpx.Response(503),
            ),
            "HTTP 503",
        ),
        (httpx.ConnectError("boom"), "unreachable"),
    ],
)
async def test_errors_become_short_tool_errors(exc, message):
    with pytest.raises(ToolError, match=message):
        await _raising(exc)()


def test_settings_from_env(monkeypatch):
    from hl_mcp.config import load_settings

    monkeypatch.setenv("HL_NETWORK", "Testnet")
    monkeypatch.setenv("HL_DEFAULT_ADDRESS", "")
    s = load_settings()
    assert s.network == "testnet"
    assert s.default_address is None

    monkeypatch.setenv("HL_NETWORK", "devnet")
    with pytest.raises(ValueError, match="HL_NETWORK"):
        load_settings()
