import asyncio
from decimal import Decimal

import httpx
from pydantic import TypeAdapter

from .constants import BASE_URLS
from .models import (
    AssetCtx,
    Candle,
    ClearinghouseState,
    Fill,
    FundingHistoryEntry,
    L2Book,
    Meta,
    PerpDex,
    UserFunding,
)
from .types import Network

RETRY_STATUSES = {429, 500, 502, 503, 504}

_META_AND_CTXS = TypeAdapter(tuple[Meta, list[AssetCtx]])
_FILLS = TypeAdapter(list[Fill])
_USER_FUNDING = TypeAdapter(list[UserFunding])
_FUNDING_HISTORY = TypeAdapter(list[FundingHistoryEntry])
_CANDLES = TypeAdapter(list[Candle])
_MIDS = TypeAdapter(dict[str, Decimal])
_PERP_DEXS = TypeAdapter(list[PerpDex | None])


class HyperliquidClient:
    """Underlying Hyperliquid API"""

    def __init__(
        self,
        network: Network = "mainnet",
        *,
        http: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        timeout: float = 5.0,
    ):
        self.http = http or httpx.AsyncClient(
            base_url=BASE_URLS[network], timeout=timeout
        )
        self.max_retries = max_retries

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.http.aclose()

    async def _post(self, body: dict):
        for tries in range(self.max_retries + 1):
            try:
                res = await self.http.post(
                    "/info", json={k: v for k, v in body.items() if v is not None}
                )
            except httpx.TransportError:
                if tries == self.max_retries:
                    raise
            else:
                if res.status_code not in RETRY_STATUSES or tries == self.max_retries:
                    res.raise_for_status()
                    return res.json()
            await asyncio.sleep(0.5 * 2**tries)

    async def l2_book(self, coin: str) -> L2Book:
        data = await self._post({"type": "l2Book", "coin": coin})
        return L2Book.model_validate(data)

    async def meta(self, dex: str | None = None) -> Meta:
        data = await self._post({"type": "meta", "dex": dex})
        return Meta.model_validate(data)

    async def perp_dexs(self) -> list[PerpDex | None]:
        """All perp dexes; the first entry is None and stands for the main dex."""
        data = await self._post({"type": "perpDexs"})
        return _PERP_DEXS.validate_python(data)

    async def meta_and_asset_ctxs(
        self, dex: str | None = None
    ) -> tuple[Meta, list[AssetCtx]]:
        data = await self._post({"type": "metaAndAssetCtxs", "dex": dex})
        return _META_AND_CTXS.validate_python(data)

    async def clearinghouse_state(
        self, user: str, dex: str | None = None
    ) -> ClearinghouseState:
        data = await self._post(
            {"type": "clearinghouseState", "user": user, "dex": dex}
        )
        return ClearinghouseState.model_validate(data)

    async def user_fills(
        self, user: str, aggregate_by_time: bool = False
    ) -> list[Fill]:
        data = await self._post(
            {"type": "userFills", "user": user, "aggregateByTime": aggregate_by_time}
        )
        return _FILLS.validate_python(data)

    async def user_fills_by_time(
        self,
        user: str,
        start_time: int,
        end_time: int | None = None,
        aggregate_by_time: bool = False,
    ) -> list[Fill]:
        data = await self._post(
            {
                "type": "userFillsByTime",
                "user": user,
                "startTime": start_time,
                "endTime": end_time,
                "aggregateByTime": aggregate_by_time,
            }
        )
        return _FILLS.validate_python(data)

    async def user_funding(
        self, user: str, start_time: int, end_time: int | None = None
    ) -> list[UserFunding]:
        data = await self._post(
            {
                "type": "userFunding",
                "user": user,
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        return _USER_FUNDING.validate_python(data)

    async def funding_history(
        self, coin: str, start_time: int, end_time: int | None = None
    ) -> list[FundingHistoryEntry]:
        data = await self._post(
            {
                "type": "fundingHistory",
                "coin": coin,
                "startTime": start_time,
                "endTime": end_time,
            }
        )
        return _FUNDING_HISTORY.validate_python(data)

    async def candle_snapshot(
        self,
        coin: str,
        interval: str,
        start_time: int,
        end_time: int,
        dex: str | None = None,
    ) -> list[Candle]:
        data = await self._post(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": f"{dex}:{coin}" if dex else coin,
                    "interval": interval,
                    "startTime": start_time,
                    "endTime": end_time,
                },
            }
        )
        return _CANDLES.validate_python(data)

    async def all_mids(self, dex: str | None = None) -> dict[str, Decimal]:
        data = await self._post({"type": "allMids", "dex": dex})
        return _MIDS.validate_python(data)

    # async def user_open_orders(self, user: str, dex: str):
    #     # if not validate_user(user):
    #     #     return xxx
    #     return await self._post({"type": "openOrders", "user": user, "dex": dex})
