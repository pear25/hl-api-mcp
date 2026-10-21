from typing import Literal

Network = Literal["mainnet"] | Literal["testnet"]


BASE_URLS: dict[Network, str] = {
    "mainnet": "https://api.hyperliquid.xyz",
    "testnet": "https://api.hyperliquid-testnet.xyz",
}
