"""Read-only Hyperliquid MCP server (stdio).

stdout carries the MCP protocol, so nothing here may print to it; logs go to
stderr.
"""

import functools
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError

from . import tools
from .api.hl_client import HyperliquidClient
from .config import Settings, load_settings

logger = logging.getLogger("hl_mcp")

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)

Address = Annotated[
    str | None,
    Field(description="Wallet address (0x + 40 hex). Omit to use HL_DEFAULT_ADDRESS."),
]
Coin = Annotated[str, Field(description="Perp ticker, e.g. BTC, ETH, SOL.")]


class AppState:
    def __init__(self, settings: Settings, client: HyperliquidClient):
        self.settings = settings
        self.client = client


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[AppState]:
    settings = load_settings()
    async with HyperliquidClient(settings.network) as client:
        logger.info("hl-mcp started against %s", settings.network)
        yield AppState(settings, client)


mcp = MCPServer(
    "hyperliquid",
    instructions=(
        "Read-only access to Hyperliquid's public info API. These tools cannot "
        "place, modify or cancel orders. Quote figures from tool output rather "
        "than computing your own."
    ),
    lifespan=lifespan,
)


def _state(ctx: Context) -> AppState:
    return ctx.request_context.lifespan_context


def _readable_errors[**P](
    fn: Callable[P, Awaitable[str]],
) -> Callable[P, Awaitable[str]]:
    """Turn expected failures into short ToolError messages for the model."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
        try:
            return await fn(*args, **kwargs)
        except tools.HLToolError as e:
            raise ToolError(str(e)) from e
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 422:
                raise ToolError("Hyperliquid rejected the request (HTTP 422)") from e
            raise ToolError(f"Hyperliquid API error (HTTP {code}); try again") from e
        except httpx.TransportError as e:
            raise ToolError("Hyperliquid API unreachable; try again shortly") from e
        except ValidationError as e:
            logger.exception("unexpected response shape")
            raise ToolError("Hyperliquid returned an unexpected response") from e

    return wrapper


@mcp.tool(annotations=READ_ONLY)
@_readable_errors
async def get_market_snapshot(coin: Coin, ctx: Context) -> str:
    """Mark/oracle price, 24h change, funding rate, open interest and volume for
    one perp market."""
    return await tools.get_market_snapshot(_state(ctx).client, coin)


@mcp.tool(annotations=READ_ONLY)
@_readable_errors
async def get_order_book(
    coin: Coin,
    ctx: Context,
    depth: Annotated[int, Field(ge=1, le=20, description="Levels per side.")] = 10,
) -> str:
    """Top-of-book bids and asks with spread for one perp market."""
    return await tools.get_order_book(_state(ctx).client, coin, depth)


@mcp.tool(annotations=READ_ONLY)
@_readable_errors
async def get_account_summary(ctx: Context, address: Address = None) -> str:
    """Account value, position notional, effective leverage, margin used and
    withdrawable balance for a perp account."""
    s = _state(ctx)
    addr = tools.validate_address(address, s.settings.default_address)
    return await tools.get_account_summary(s.client, addr)


@mcp.tool(annotations=READ_ONLY)
@_readable_errors
async def get_positions(
    ctx: Context,
    address: Address = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> str:
    """Open perp positions, largest notional first: side, size, entry, unrealised
    PnL, leverage, liquidation price and funding since open."""
    s = _state(ctx)
    addr = tools.validate_address(address, s.settings.default_address)
    return await tools.get_positions(s.client, addr, limit)


@mcp.tool(annotations=READ_ONLY)
@_readable_errors
async def get_recent_fills(
    ctx: Context,
    address: Address = None,
    since_hours: Annotated[float, Field(gt=0, le=24 * 90)] = 24,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> str:
    """Recent trades (newest first) with closed PnL and fees, plus window totals.
    Partial fills of the same order are aggregated."""
    s = _state(ctx)
    addr = tools.validate_address(address, s.settings.default_address)
    return await tools.get_recent_fills(s.client, addr, since_hours, limit)


@mcp.tool(annotations=READ_ONLY)
@_readable_errors
async def get_funding_payments(
    ctx: Context,
    address: Address = None,
    since_hours: Annotated[float, Field(gt=0, le=24 * 90)] = 168,
) -> str:
    """Funding paid or received over a window, net and per coin
    (positive = received, negative = paid)."""
    s = _state(ctx)
    addr = tools.validate_address(address, s.settings.default_address)
    return await tools.get_funding_payments(s.client, addr, since_hours)


def main() -> None:
    logging.basicConfig(level=logging.INFO)  # stderr by default
    logging.getLogger("httpx").setLevel(logging.WARNING)
    mcp.run("stdio")


if __name__ == "__main__":
    main()
