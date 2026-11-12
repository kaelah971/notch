"""Notch Trend Radar — free-source attention discovery (S3A).

Discovery only. This package never creates markets, signs transactions, or
produces settlement evidence. It produces ranked, evidence-linked candidates
and PROPOSED market drafts for operator review.
"""

from .service import ScanConfig, TrendRadarService
from .http import FixtureFetcher, LiveFetcher, make_fetcher
from .store import RadarStore

__version__ = "0.1.0"

__all__ = [
    "FixtureFetcher",
    "LiveFetcher",
    "RadarStore",
    "ScanConfig",
    "TrendRadarService",
    "make_fetcher",
]
