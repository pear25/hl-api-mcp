from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

### start assetMeta


class AssetMeta(BaseModel):
    name: str
    szDecimals: int
    maxLeverage: int
    marginTableId: int
    onlyIsolated: bool | None = None
    marginMode: str | None = None
    isDelisted: bool = False


class MarginTiers(BaseModel):
    lowerBound: Decimal
    maxLeverage: int


class MarginTableObject(BaseModel):
    description: str
    marginTiers: list[MarginTiers]


class Meta(BaseModel):
    universe: list[AssetMeta]
    marginTables: list[tuple[int, MarginTableObject]]
    collateralToken: int | None = None


### end assetMeta

### start perpDexs


class PerpDex(BaseModel):
    name: str
    fullName: str
    deployer: str


### end perpDexs

### start metaAndAssetCtxs


class AssetCtx(BaseModel):
    funding: Decimal
    openInterest: Decimal
    prevDayPx: Decimal
    dayNtlVlm: Decimal
    premium: Decimal | None = None
    oraclePx: Decimal
    markPx: Decimal
    midPx: Decimal | None = None
    impactPxs: list[Decimal] | None = None
    dayBaseVlm: Decimal


### end metaAndAssetCtxs

### start l2Book


class L2Level(BaseModel):
    px: Decimal
    sz: Decimal
    n: int


class L2Book(BaseModel):
    coin: str
    time: datetime
    levels: tuple[list[L2Level], list[L2Level]]  # (bids, asks)


### end l2Book

### start clearinghouseState


class CumulativeFunding(BaseModel):
    allTime: Decimal
    sinceChange: Decimal
    sinceOpen: Decimal


class Leverage(BaseModel):
    rawUsd: Decimal | None = None
    type: str
    value: int


class AssetPosition(BaseModel):
    coin: str
    cumFunding: CumulativeFunding
    entryPx: Decimal
    leverage: Leverage
    liquidationPx: Decimal | None = None
    marginUsed: Decimal
    maxLeverage: int
    positionValue: Decimal
    returnOnEquity: Decimal
    szi: Decimal
    unrealizedPnl: Decimal


class AssetPositions(BaseModel):
    position: AssetPosition
    type: str


class MarginSummary(BaseModel):
    accountValue: Decimal
    totalMarginUsed: Decimal
    totalNtlPos: Decimal
    totalRawUsd: Decimal


class ClearinghouseState(BaseModel):
    assetPositions: list[AssetPositions]
    crossMaintenanceMarginUsed: Decimal
    crossMarginSummary: MarginSummary
    marginSummary: MarginSummary
    time: datetime
    withdrawable: Decimal


### end clearinghouseState

### start userFills


class Fill(BaseModel):
    coin: str
    px: Decimal
    sz: Decimal
    side: Literal["A", "B"]  # A = ask (sell), B = bid (buy)
    time: datetime
    startPosition: Decimal
    dir: str
    closedPnl: Decimal
    hash: str
    oid: int
    crossed: bool
    fee: Decimal
    tid: int
    feeToken: str
    twapId: int | None = None
    builderFee: Decimal | None = None


### end userFills

### start userFunding


class FundingDelta(BaseModel):
    type: str
    coin: str
    usdc: Decimal  # positive = received, negative = paid
    szi: Decimal
    fundingRate: Decimal
    nSamples: int | None = None


class UserFunding(BaseModel):
    time: datetime
    hash: str
    delta: FundingDelta


### end userFunding

### start fundingHistory


class FundingHistoryEntry(BaseModel):
    coin: str
    fundingRate: Decimal
    premium: Decimal
    time: datetime


### end fundingHistory

### start candleSnapshot


class Candle(BaseModel):
    t: datetime  # open time
    T: datetime  # close time
    s: str
    i: str
    o: Decimal
    c: Decimal
    h: Decimal
    l: Decimal  # noqa: E741
    v: Decimal
    n: int


### end candleSnapshot
