"""Discovery source adapters."""

from .coingecko import CoinGeckoAdapter
from .hackernews import HackerNewsAdapter

__all__ = ["CoinGeckoAdapter", "HackerNewsAdapter"]
