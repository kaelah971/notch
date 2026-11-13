"""Deterministic tests for finalized Pulse indexing and analytics."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from services.intents.balance import NearRpcError
from services.web_api.pulse import PulseIndexer, PulseStore


class FakeRpc:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.blocks = {
            100: self.block(100, "block-100", 1_700_000_000_000_000_000, ["chunk-100"]),
            101: self.block(101, "block-101", 1_700_000_060_000_000_000, ["chunk-101"]),
        }
        self.chunks = {
            "chunk-100": {
                "transactions": [
                    self.transaction("tx-good", "alice.testnet", "1", "market-a", 0),
                    self.transaction("tx-good-2", "alice.testnet", "1", "market-a", 0),
                ],
            },
            "chunk-101": {
                "transactions": [self.transaction("tx-failed", "bob.testnet", "2", "market-a", 1)],
            },
        }
        self.statuses = {
            "tx-good": self.status(
                "tx-good",
                "receipt-good",
                "receipt-block-good",
                "alice.testnet",
                "market-a",
                0,
                "1000000",
                success=True,
            ),
            "tx-good-2": self.status(
                "tx-good-2",
                "receipt-good-2",
                "receipt-block-good",
                "alice.testnet",
                "market-a",
                0,
                "1000000",
                success=True,
            ),
            "tx-failed": self.status(
                "tx-failed",
                "receipt-failed",
                "receipt-block-failed",
                "bob.testnet",
                "market-a",
                1,
                "2000000",
                success=False,
            ),
        }
        self.receipt_blocks = {
            "receipt-block-good": self.block(
                100, "receipt-block-good", 1_700_000_001_000_000_000, []
            ),
            "receipt-block-failed": self.block(
                101, "receipt-block-failed", 1_700_000_061_000_000_000, []
            ),
        }

    @staticmethod
    def block(height: int, block_hash: str, timestamp: int, chunks: list[str]) -> dict:
        return {
            "header": {"height": height, "hash": block_hash, "timestamp": timestamp},
            "chunks": [{"chunk_hash": chunk} for chunk in chunks],
        }

    @staticmethod
    def transaction(tx_hash: str, signer: str, amount: str, market_id: str, outcome: int) -> dict:
        args = {
            "receiver_id": "market.notch-dev.testnet",
            "amount": str(int(amount) * 1_000_000),
            "msg": json.dumps({"market_id": market_id, "outcome": outcome}, separators=(",", ":")),
        }
        encoded = base64.b64encode(json.dumps(args, separators=(",", ":")).encode()).decode()
        return {
            "hash": tx_hash,
            "signer_id": signer,
            "receiver_id": "usdc.tidepool-sandbox.testnet",
            "actions": [{"FunctionCall": {"method_name": "ft_transfer_call", "args": encoded}}],
        }

    @staticmethod
    def status(
        tx_hash: str,
        receipt_id: str,
        receipt_block: str,
        account: str,
        market_id: str,
        outcome: int,
        amount: str,
        *,
        success: bool,
    ) -> dict:
        if not success:
            return {
                "status": {"Failure": {"ActionError": {"kind": {"FunctionCallError": {}}}}},
                "transaction": {"hash": tx_hash},
                "receipts_outcome": [],
            }
        log = "EVENT_JSON:" + json.dumps(
            {
                "standard": "notch-market",
                "version": "1.0.0",
                "event": "position_entered",
                "data": {
                    "market_id": market_id,
                    "account_id": account,
                    "outcome": outcome,
                    "amount": amount,
                    "sender_id": account,
                    "predecessor": "usdc.tidepool-sandbox.testnet",
                },
            },
            separators=(",", ":"),
        )
        return {
            "status": {"SuccessValue": ""},
            "transaction": {"hash": tx_hash},
            "receipts_outcome": [
                {
                    "id": receipt_id,
                    "block_hash": receipt_block,
                    "outcome": {
                        "executor_id": "market.notch-dev.testnet",
                        "status": {"SuccessValue": ""},
                        "logs": [log],
                    },
                }
            ],
        }

    def _rpc(self, method: str, params: object):
        self.calls.append((method, params))
        if method == "block" and params == {"finality": "final"}:
            return self.blocks[101]
        if method == "block" and isinstance(params, dict):
            block_id = params["block_id"]
            if block_id in self.blocks:
                return self.blocks[block_id]
            return self.receipt_blocks[block_id]
        if method == "chunk":
            return self.chunks[params["chunk_id"]]
        if method == "EXPERIMENTAL_tx_status":
            return self.statuses[params[0]]
        raise AssertionError((method, params))


class PulseTests(unittest.TestCase):
    def test_indexes_only_successful_finalized_events_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PulseStore(Path(directory) / "pulse.sqlite3")
            rpc = FakeRpc()
            indexer = PulseIndexer(
                rpc=rpc,
                store=store,
                market_contract="market.notch-dev.testnet",
                collateral_token="usdc.tidepool-sandbox.testnet",
                start_block=100,
                max_blocks=10,
            )
            first = indexer.sync()
            self.assertIsNone(first.error)
            self.assertEqual(first.scanned_blocks, 2)
            self.assertEqual(first.events_found, 2)
            self.assertEqual(store.cursor_height(), 101)

            summary = store.summary(window="all")
            self.assertEqual(summary["metrics"]["forecaster_count"], 1)
            self.assertEqual(summary["metrics"]["new_forecaster_count"], 1)
            self.assertEqual(summary["metrics"]["confirmed_volume_base_units"], "2000000")
            self.assertEqual(summary["metrics"]["successful_entries"], 1)
            self.assertEqual(summary["metrics"]["successful_entry_events"], 2)
            self.assertEqual(len(summary["recent_calls"]), 2)
            self.assertEqual(summary["participants"][0]["account_id"], "alice.testnet")
            self.assertEqual(summary["participants"][0]["successful_entries"], 1)
            self.assertEqual(summary["participants"][0]["successful_entry_events"], 2)
            self.assertEqual({call["tx_hash"] for call in summary["recent_calls"]}, {"tx-good", "tx-good-2"})
            self.assertEqual(summary["recent_calls"][0]["verification"], "finalized_position_entered_event")
            self.assertEqual(summary["coverage"]["indexed_event_count"], 2)

            second = indexer.sync()
            self.assertEqual(second.scanned_blocks, 0)
            self.assertEqual(store.summary(window="all")["metrics"]["successful_entries"], 1)
            self.assertEqual(store.summary(window="all")["metrics"]["successful_entry_events"], 2)
            indexer.close()

    def test_cursor_stays_at_last_completed_block_when_rpc_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PulseStore(Path(directory) / "pulse.sqlite3")
            rpc = FakeRpc()
            original = rpc._rpc
            failed = {"value": False}

            def flaky(method, params):
                if failed["value"] and method == "block" and params == {"block_id": 101}:
                    raise NearRpcError("temporary outage")
                return original(method, params)

            rpc._rpc = flaky  # type: ignore[method-assign]
            indexer = PulseIndexer(
                rpc=rpc,
                store=store,
                market_contract="market.notch-dev.testnet",
                collateral_token="usdc.tidepool-sandbox.testnet",
                start_block=100,
                max_blocks=1,
            )
            first = indexer.sync()
            self.assertEqual(first.to_height, 100)
            self.assertEqual(store.cursor_height(), 100)
            failed["value"] = True
            second = indexer.sync()
            self.assertIsNotNone(second.error)
            self.assertEqual(store.cursor_height(), 100)
            self.assertEqual(store.coverage()["status"], "degraded")
            indexer.close()

    def test_no_configured_start_block_establishes_boundary_without_backfill(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PulseStore(Path(directory) / "pulse.sqlite3")
            indexer = PulseIndexer(
                rpc=FakeRpc(),
                store=store,
                market_contract="market.notch-dev.testnet",
                collateral_token="usdc.tidepool-sandbox.testnet",
            )
            result = indexer.sync()
            self.assertTrue(result.initialized)
            self.assertEqual(result.scanned_blocks, 0)
            self.assertEqual(store.summary(window="all")["metrics"]["successful_entries"], 0)
            self.assertFalse(store.coverage()["historical_backfill"])
            indexer.close()


if __name__ == "__main__":
    unittest.main()
