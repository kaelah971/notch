import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from services.trend_radar.http import FixtureFetcher
from services.trend_radar.models import EligibilityStatus, SourceStatus
from services.trend_radar.service import ScanConfig, TrendRadarService
from services.trend_radar.store import RadarStore
from services.trend_radar.tests.helpers import (
    FIXED_NOW,
    FailingFetcher,
    StaleFetcher,
    fixture_fetcher,
)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RadarStore(Path(self.temp.name) / "radar.sqlite3")
        self.now = [FIXED_NOW]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def service(self, fetcher, config=None):
        return TrendRadarService(
            fetcher=fetcher,
            store=self.store,
            config=config or ScanConfig(),
            now_fn=lambda: self.now[0],
        )

    def test_full_fixture_scan(self):
        result = self.service(fixture_fetcher()).scan()
        self.assertEqual(result["scan_kind"], "fixture")
        self.assertEqual(result["scan_date"], "2026-11-11")
        self.assertEqual(
            [(h["source"], h["status"]) for h in result["source_health"]],
            [("wikimedia", "ok"), ("coingecko", "ok"), ("hackernews", "ok")],
        )
        self.assertEqual(len(result["candidates"]), 9)
        eligible = [
            c for c in result["candidates"] if c["eligibility_status"] == "ELIGIBLE"
        ]
        self.assertEqual(
            sorted(c["title"] for c in eligible),
            ["Artificial intelligence", "Bitcoin", "ChatGPT", "Nvidia"],
        )
        nvidia = next(c for c in result["candidates"] if c["title"] == "Nvidia")
        self.assertEqual(nvidia["discovery_signals"]["source_count"], 2)
        self.assertEqual(nvidia["discovery_signals"]["sources"], ["wikimedia", "hackernews"])
        self.assertEqual(len(nvidia["source_identities"]), 2)
        self.assertTrue(
            any(item.get("story_id") == "50459703" for item in nvidia["source_identities"])
        )
        self.assertTrue(
            any(item.get("page_id") == 39120 for item in nvidia["source_identities"])
        )
        self.assertEqual(nvidia["proposed_market_modes"], ["trend_trading", "trend_battle"])
        self.assertEqual(len(result["proposals"]), 9)
        self.assertTrue(all(p["status"] == "PROPOSED" for p in result["proposals"]))
        self.assertTrue(all(p["rule_hash"] is None for p in result["proposals"]))
        self.assertEqual(result["last_successful_update"], "2026-11-11T23:45:00Z")
        self.assertIn("categories", result["source_context"]["coingecko"])
        self.assertTrue(result["source_context"]["coingecko"]["categories"])
        self.assertTrue(result["source_context"]["coverage_probes"])
        self.assertTrue(all(c["proposed_market_modes"] for c in eligible))
        self.assertFalse(any("market_created" in str(c) for c in result["candidates"]))

    def test_duplicate_scan_is_deduplicated(self):
        service = self.service(fixture_fetcher())
        first = service.scan()
        second = service.scan()
        self.assertFalse(first["deduplicated"])
        self.assertTrue(second["deduplicated"])
        self.assertEqual(first["scan_id"], second["scan_id"])
        self.assertEqual(len(first["candidates"]), len(second["candidates"]))

    def test_replay_is_deterministic(self):
        first = self.service(fixture_fetcher()).scan()
        second_store = RadarStore(Path(self.temp.name) / "radar2.sqlite3")
        try:
            second_service = TrendRadarService(
                fetcher=fixture_fetcher(),
                store=second_store,
                config=ScanConfig(),
                now_fn=lambda: FIXED_NOW,
            )
            second = second_service.scan()
        finally:
            second_store.close()
        self.assertEqual(first["scan_id"], second["scan_id"])
        self.assertEqual(
            [(c["candidate_id"], c["title"], c["eligibility_status"],
              c["discovery_signals"]["score"], c["proposed_market_modes"])
             for c in first["candidates"]],
            [(c["candidate_id"], c["title"], c["eligibility_status"],
              c["discovery_signals"]["score"], c["proposed_market_modes"])
             for c in second["candidates"]],
        )
        self.assertEqual(
            [(p["proposal_id"], p["mode"], p["status"], p["question"])
             for p in first["proposals"]],
            [(p["proposal_id"], p["mode"], p["status"], p["question"])
             for p in second["proposals"]],
        )

    def test_partial_provider_failure_is_isolated(self):
        fetcher = FailingFetcher({"coingecko"}, fixture_fetcher())
        result = self.service(fetcher).scan()
        health = {h["source"]: h for h in result["source_health"]}
        self.assertEqual(health["coingecko"]["status"], "failed")
        self.assertTrue(health["coingecko"]["rate_limited"])
        self.assertEqual(health["wikimedia"]["status"], "ok")
        self.assertEqual(health["hackernews"]["status"], "ok")
        titles = {c["title"] for c in result["candidates"]}
        self.assertIn("Nvidia", titles)
        self.assertIn("ChatGPT", titles)
        self.assertNotIn("Bitcoin", titles)
        self.assertEqual(
            [c["eligibility_status"] for c in result["candidates"] if c["title"] == "Nvidia"],
            ["ELIGIBLE"],
        )
        self.assertTrue(result["proposals"])

    def test_all_provider_failure_does_not_fabricate_candidates(self):
        fetcher = FailingFetcher({"wikimedia", "coingecko", "hackernews"})
        result = self.service(fetcher).scan()
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["proposals"], [])
        self.assertTrue(all(h["status"] == "failed" for h in result["source_health"]))
        self.assertTrue(result["errors"])

    def test_stale_cache_is_marked_and_not_eligible(self):
        result = self.service(StaleFetcher(fixture_fetcher())).scan()
        self.assertTrue(all(h["stale"] for h in result["source_health"] if h["status"] != "skipped"))
        statuses = {c["eligibility_status"] for c in result["candidates"]}
        self.assertIn("STALE", statuses)
        self.assertNotIn("ELIGIBLE", statuses)
        self.assertEqual(result["proposals"], [])

    def test_probe_limit_bounds_eligibility(self):
        result = self.service(
            fixture_fetcher(), ScanConfig(probe_limit=1)
        ).scan()
        probed = result["source_context"]["coverage_probes"]
        self.assertEqual(len(probed), 1)
        eligible = [c for c in result["candidates"] if c["eligibility_status"] == "ELIGIBLE"]
        self.assertLessEqual(len(eligible), 1)
        self.assertTrue(
            any("coverage_probe_not_run" in c["eligibility_reasons"] for c in result["candidates"])
        )

    def test_decisions_survive_rescan(self):
        service = self.service(fixture_fetcher())
        result = service.scan()
        proposal = next(
            p for p in result["proposals"] if p["mode"] == "trend_trading"
        )
        reviewed = service.review_proposal(
            proposal["proposal_id"], "approve", "ready for S3B review"
        )
        self.assertEqual(reviewed["status"], "APPROVED")
        self.now[0] = FIXED_NOW + timedelta(minutes=1)
        rescanned = service.scan(force=True)
        persisted = next(
            p for p in rescanned["proposals"]
            if p["proposal_id"] == proposal["proposal_id"]
        )
        self.assertEqual(persisted["status"], "APPROVED")
        self.assertEqual(persisted["decision_reason"], "ready for S3B review")

    def test_failed_source_retains_previous_success_and_snapshots(self):
        first = self.service(fixture_fetcher()).scan()
        nvidia_id = next(c["candidate_id"] for c in first["candidates"] if c["title"] == "Nvidia")
        self.now[0] = FIXED_NOW + timedelta(minutes=1)
        failing = FailingFetcher({"coingecko"}, fixture_fetcher())
        second = self.service(failing).scan(force=True)
        coin_health = next(h for h in second["source_health"] if h["source"] == "coingecko")
        self.assertEqual(coin_health["status"], "failed")
        self.assertEqual(coin_health["last_success_at"], "2026-11-11T23:45:00Z")
        self.assertIsNotNone(self.store.get_source_snapshot("coingecko"))
        self.assertIsNotNone(self.store.get_candidate(nvidia_id))

    def test_scan_result_required_outputs(self):
        result = self.service(fixture_fetcher()).scan()
        for key in (
            "candidates",
            "source_health",
            "source_context",
            "proposals",
            "last_successful_update",
            "scan_kind",
            "scan_date",
        ):
            self.assertIn(key, result)
        for candidate in result["candidates"]:
            for key in (
                "candidate_id",
                "canonical_topic_id",
                "title",
                "category",
                "aliases",
                "source_identities",
                "discovery_evidence",
                "source_urls",
                "first_seen_at",
                "last_seen_at",
                "observed_at",
                "discovery_signals",
                "eligibility_status",
                "eligibility_reasons",
                "confidence",
                "reliability",
                "proposed_market_modes",
            ):
                self.assertIn(key, candidate)


if __name__ == "__main__":
    unittest.main()
