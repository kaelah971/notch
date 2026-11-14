import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from services.web_api.snapshots import SnapshotStore
from services.web_api.tests.test_api import NOW_NS, OPEN_ID, make_app


class MarketHistoryAPITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = make_app()
        self.snapshots = SnapshotStore(Path(self.tmp.name) / "history.sqlite3")
        self.app.snapshots = self.snapshots

    def tearDown(self):
        self.app.close()
        self.snapshots._db.close()
        self.tmp.cleanup()

    def call(self, path):
        parsed = urlparse(path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        return self.app.handle("GET", parsed.path, query, None, client="history-test")

    def test_history_is_frontend_compatible_and_source_backed(self):
        status, _ = self.call("/api/markets")
        self.assertEqual(status, 200)

        status, payload = self.call(f"/api/markets/{OPEN_ID}/history")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["market_id"], OPEN_ID)
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertTrue(payload["meta"]["recording"])
        self.assertIn("pool totals read from the market contract", payload["meta"]["source"])
        point = payload["data"][0]
        self.assertEqual(point["block_ts_ns"], str(NOW_NS))
        self.assertEqual(point["totals"], ["0", "0"])
        self.assertEqual(point["status"], "open")
        self.assertIn("observed_at_utc", point)

    def test_known_market_with_no_records_is_explicitly_empty(self):
        status, payload = self.call(f"/api/markets/{OPEN_ID}/history")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"], [])
        self.assertEqual(payload["meta"]["count"], 0)
        self.assertTrue(payload["meta"]["recording"])

    def test_unknown_market_and_invalid_configuration_are_not_successful_empty_history(self):
        status, payload = self.call("/api/markets/not-a-real-market/history")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "MARKET_NOT_FOUND")

        self.app.snapshots = None
        status, payload = self.call(f"/api/markets/{OPEN_ID}/history")
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"]["code"], "HISTORY_UNAVAILABLE")

    def test_existing_market_reads_remain_intact(self):
        status, payload = self.call("/api/markets")
        self.assertEqual(status, 200)
        self.assertEqual(payload["meta"]["count"], 2)

        status, payload = self.call(f"/api/markets/{OPEN_ID}")
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["market_id"], OPEN_ID)


if __name__ == "__main__":
    unittest.main()
