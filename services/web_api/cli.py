"""Start the S6 frontend-ready API server."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from services.intents.balance import NearRpcClient
from services.intents.client import RateLimiter as FundingRateLimiter, TidepoolClient
from services.intents.config import IntentsConfig
from services.intents.service import IntentsFundingService
from services.intents.official import OfficialMainnetFundingService
from services.intents.store import FundingStore
from services.creator_notes.service import CreatorNotesService
from services.creator_notes.store import CreatorNotesStore
from services.near_ai.client import NearAIClient
from services.near_ai.config import NearAIConfig
from services.near_ai.service import BriefService
from services.near_ai.store import BriefStore
from services.research_council.service import ResearchCouncilService
from services.research_council.store import ResearchCouncilStore
from services.trend_radar.http import LiveFetcher
from services.web_api.app import WebAPI
from services.web_api.chain import MarketChainReader
from services.web_api.config import WebAPIConfig
from services.web_api.repositories import OracleRepository, RadarRepository
from services.web_api.pulse import PulseIndexer, PulseStore
from services.web_api.server import serve


def build_default_app(config: WebAPIConfig | None = None) -> WebAPI:
    config = config or WebAPIConfig.from_env()
    intents = IntentsConfig.from_env()
    intents = replace(
        intents,
        market_contract=config.market_contract,
        rpc_url=config.rpc_url,
        data_dir=str(Path(intents.data_dir)),
    )
    funding_store = FundingStore(Path(intents.data_dir) / "funding.sqlite3")
    funding_client = TidepoolClient(
        base_url=intents.base_url,
        api_key=intents.api_key,
        timeout_seconds=intents.request_timeout_seconds,
        max_retries=intents.max_retries,
        rate_limiter=FundingRateLimiter(interval_seconds=intents.rate_limit_seconds),
    )
    chain_reader = NearRpcClient(
        rpc_url=intents.rpc_url,
        timeout_seconds=intents.request_timeout_seconds,
    )
    funding_service = IntentsFundingService(
        client=funding_client,
        store=funding_store,
        config=intents,
        reader=chain_reader,
    )

    official_funding_service = OfficialMainnetFundingService.from_env()

    ai = NearAIConfig.from_env()
    ai = replace(
        ai,
        radar_db=config.radar_db,
        oracle_db=config.oracle_db_paths[0],
        data_dir=str(Path(ai.data_dir)),
    )
    brief_store = BriefStore(Path(ai.data_dir) / "briefs.sqlite3")
    ai_client = NearAIClient(config=ai)
    brief_service = BriefService(
        config=ai,
        client=ai_client,
        store=brief_store,
    )
    council_service = ResearchCouncilService(
        config=ai,
        client=ai_client,
        store=ResearchCouncilStore(config.council_db_path),
    )

    chain = MarketChainReader(config=intents, reader=chain_reader)
    radar = RadarRepository(config.radar_db)
    oracle = OracleRepository(config.oracle_db_paths)
    attention_fetcher = LiveFetcher(
        Path(config.radar_db).parent,
        timeout_seconds=config.request_timeout_seconds,
        max_retries=1,
    )
    creator_notes = CreatorNotesService(
        store=CreatorNotesStore(config.creator_notes_db_path),
        reader=chain_reader,
        chain=chain,
        radar=radar,
        payment_token=config.collateral_token,
        payment_network=config.network,
    )
    pulse = PulseIndexer(
        rpc=chain_reader,
        store=PulseStore(config.pulse_db_path),
        market_contract=config.market_contract,
        collateral_token=config.collateral_token,
        start_block=config.pulse_start_block,
        max_blocks=config.pulse_max_blocks_per_request,
    )
    return WebAPI(
        attention_fetcher=attention_fetcher,
        config=config,
        chain=chain,
        radar=radar,
        oracle=oracle,
        brief_service=brief_service,
        funding_service=funding_service,
        official_funding_service=official_funding_service,
        creator_notes_service=creator_notes,
        council_service=council_service,
        pulse=pulse,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="notch-web-api",
        description="S6 frontend-ready HTTP API for Notch testnet data.",
    )
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    config = WebAPIConfig.from_env()
    if args.host:
        config = replace(config, host=args.host)
    if args.port:
        config = replace(config, port=args.port)
    app = build_default_app(config)
    print(
        f"Notch S6 API listening on http://{config.host}:{config.port} "
        f"(network={config.network})"
    )
    try:
        serve(app, host=config.host, port=config.port)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
