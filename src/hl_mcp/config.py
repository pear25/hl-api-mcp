import os
from dataclasses import dataclass
from typing import Literal, get_args

from dotenv import find_dotenv, load_dotenv

from .api.types import Network


@dataclass(frozen=True)
class Settings:
    network: Network
    default_address: str | None


def load_settings() -> Settings:
    """Read settings from the environment, falling back to a .env in the cwd."""
    load_dotenv(find_dotenv(usecwd=True))
    network: Literal["mainnet"] | Literal["testnet"] = (
        os.getenv("HL_NETWORK", "mainnet").strip().lower()
    )  # type: ignore
    if network not in get_args(Network):
        raise ValueError(f"HL_NETWORK must be mainnet or testnet, got {network!r}")
    default_address = os.getenv("HL_DEFAULT_ADDRESS", "").strip() or None
    return Settings(network=network, default_address=default_address)
