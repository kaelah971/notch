import tempfile
import unittest
from pathlib import Path

from services.web_api.snapshots import HEARTBEAT_NS, SnapshotStore


class SnapshotStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SnapshotStore(Path(self.tmp.name) / "s.sqlite3")

    def tearDown(self):
        self.store._db.close()
        self.tmp.cleanup()

    def m(self, totals, status="open"):
        return {"market_id": "mk", "totals": totals, "status": status}

    def test_records_only_changes_and_hourly_heartbeat(self):
        self.store.record(self.m(["0", "0"]), 1_000)
        self.store.record(self.m(["0", "0"]), 2_000)  # unchanged, < 1h: skipped
        self.store.record(self.m(["1000000", "0"]), 3_000)  # changed: kept
        self.store.record(self.m(["1000000", "0"]), 3_000 + HEARTBEAT_NS)  # heartbeat: kept
        h = self.store.history("mk")
        self.assertEqual([p["block_ts_ns"] for p in h], ["1000", "3000", str(3_000 + HEARTBEAT_NS)])
        self.assertEqual(h[1]["totals"], ["1000000", "0"])

    def test_never_writes_out_of_order_or_empty(self):
        self.store.record(self.m(["5", "0"]), 10_000)
        self.store.record(self.m(["6", "0"]), 9_000)  # older block: ignored
        self.store.record({"market_id": "mk", "totals": []}, 11_000)
        self.assertEqual(len(self.store.history("mk")), 1)


if __name__ == "__main__":
    unittest.main()
