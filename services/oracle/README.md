# Notch Deterministic Attention Oracle (S3B)

Backend-only oracle for Trend Trading and Trend Battles. It calibrates thresholds
from historical Wikimedia pageviews, freezes canonical rules, computes replay
and future evidence receipts, verifies digests and prepares exact S2 contract
calls. It **never signs or submits a transaction** and never creates a market.

Python standard library only.

## Quick start

```bash
# Offline recorded-fixture demo (no network)
python -m services.oracle --data-dir var/oracle \
  --now 2026-11-12T02:00:00Z \
  --fixtures services/oracle/fixtures \
  demo --summary

# Live Wikimedia smoke (no onchain action)
python -m services.oracle --data-dir var/oracle_live \
  --now 2026-11-12T02:00:00Z --calibration-end 2026-11-10 demo --summary

# Verify a receipt
python -m services.oracle verify-evidence var/oracle/evidence/<receipt>.json

# Operator approval (local only)
python -m services.oracle --data-dir var/oracle approve-rule <rule_hash> \
  --reason "reviewed for S2.5" --operator notch-dev.testnet

# Read the deployed market and prepare exact resolution args (no send)
python -m services.oracle --data-dir var/oracle prepare-resolution \
  --rule-hash <rule_hash> --evidence-digest <evidence_digest> --onchain
```

The global `--data-dir`, `--fixtures`, `--now` and `--s3a-evidence` options come
before the subcommand.

## Outcomes

| Mode | Evidence outcome | Prepared S2 action |
| --- | --- | --- |
| Trend Trading | UP / DOWN | `resolve_market` with outcome 0 / 1 |
| Trend Trading | INVALID | `void_market` with the evidence digest as reason hash |
| Trend Battle | TOPIC_A / TOPIC_B | `resolve_market` with outcome 0 / 1 |
| Trend Battle | TIE | `resolve_tie` |
| Trend Battle | INVALID | `void_market` |

The S2 contract's `evidence_hash` and `reason_hash` require
`sha256:<64 hex>`; all receipts use that form.

## Why digest reproducibility is special

The evidence/calibration digest includes source values, dates, raw response
hashes, formula inputs and rule hash, but excludes wall-clock retrieval
timestamps. Retrieval timestamps remain in the receipt. This lets a later fetch
of the same historical source data reproduce the same digest, while any source
change invalidates it.

## Tests

```bash
python -m unittest discover -s services/oracle/tests -t .
```

See [`docs/S3B_ORACLE_VERIFICATION.md`](../../docs/S3B_ORACLE_VERIFICATION.md)
for formulas, hashes, real examples, replay limitations, resolver trust and S2.5
integration.
