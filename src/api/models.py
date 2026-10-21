from datetime import datetime
from decimal import Decimal

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


### end assetMeta

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
