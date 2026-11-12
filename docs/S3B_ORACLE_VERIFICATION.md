# S3B — Deterministic Attention Oracle verification

Date: 2026-11-12 (UTC)
Status:

- **S3B implementation complete and verified locally: YES**
- **Both modes produce reproducible evidence outcomes: YES**
- **Evidence digests independently recomputable: YES**
- **Onchain market created or resolved: NO**
- **Transactions signed or submitted: NONE**
- **Proposed rules status: DRAFT / operator approval required**

The deployed S2 contract remains at `market.notch-dev.testnet`,
collateral `usdc.tidepool-sandbox.testnet`, with **market_count = 0** at the
last read. The S2.5 first market remains uncreated at its approval gate.

## 1. Architecture

```text
S3A evidence (80 candidates)
        │  Bitcoin / ChatGPT / Nvidia shortlist, source identities
        ▼
candidate review hardening ── entity/alias/parent-child/correlation
        │                       sensitivity + ambiguity + interest (informational)
        ▼
Wikimedia Pageviews range fetch ── exact UTC days, raw hashes, identity
        │
        ▼
threshold calibration (integer p75 growth; p10 absolute battle difference)
        │
        ▼
frozen market rule ── canonical UTF-8 JSON + SHA-256 rule_hash
        │
        ├── replay rule + historical observations ── evidence digest
        └── future rule ── no evidence until observation window closes
                                      │
                                      ▼
resolution preparation ── exact S2 resolve_market / resolve_tie / void_market args
        │                                  │
        └── no signing, no submission ─────┘
```

Repository layout:

```text
services/oracle/
  models.py             rule, calibration, evidence, plan, review models
  wikimedia.py          exact-range pageviews + identity retrieval
  calibration.py        reproducible historical threshold/tie calibration
  calculations.py       integer growth, trend, battle and percentile math
  rules.py              canonical rule schema, validation, S2 create args
  evidence.py           evidence receipts, digests and verification
  review.py             S3A candidate hardening and relationship checks
  contract.py           S2 RPC reads, market validation, resolution plans
  store.py              SQLite rules, calibrations, evidence, reviews, jobs
  service.py            demo / resolve / prepare / approve orchestration
  fixture_fetcher.py    raw-byte-preserving offline replay
  cli.py                backend-only CLI
  fixtures/             recorded real Wikimedia responses
  tests/                65 S3B unittest tests
```

Python standard library only. No frontend, no contract changes, no paid
services, no autonomous execution.

## 2. Formula definitions

All values are unsigned/signed integers; no floating point is used.

```text
growth_bps = floor((target_views - baseline_views) * 10000 / baseline_views)
```

Python floor division is used for negative growth as well (e.g. 3 → 1 is
`-6667`, not `-6666`).

Trend Trading:

```text
UP   if growth_bps >= frozen_threshold_bps
DOWN if growth_bps < frozen_threshold_bps
INVALID if baseline is missing, incomplete, or below minimum_baseline_views
```

Trend Battle (`growth_comparison_v1`):

```text
growth_a_bps = growth_bps(baseline_a, target_a)
growth_b_bps = growth_bps(baseline_b, target_b)
difference_bps = growth_a_bps - growth_b_bps

TIE      if abs(difference_bps) <= frozen_tie_tolerance_bps
TOPIC_A  if difference_bps >  frozen_tie_tolerance_bps
TOPIC_B  if difference_bps < -frozen_tie_tolerance_bps
INVALID  if either baseline/target is missing or below minimum
```

A tie is **not** a winner. The preparation layer maps it to the S2
`resolve_tie` call, which voids the market and enables refunds. Invalid data maps
to `void_market`, never to a winning outcome.

S2 contract outcome indices:

- Trend Trading: `UP` → `winning_outcome = 0`, `DOWN` → `1`.
- Trend Battle: `TOPIC_A` → `0`, `TOPIC_B` → `1`, `TIE` → `resolve_tie`.
- `INVALID` → `void_market`.

## 3. Source assumptions

- Source: Wikimedia Analytics Pageviews, `en.wikipedia.org`, `all-access`,
  `user`, daily granularity, UTC days.
- Identity: exact article title and page ID resolved through the MediaWiki
  Action API. The shortlist uses the S3A source identities:
  Bitcoin (28249265), ChatGPT (72417803), Nvidia (39120).
- Only complete daily observations are accepted. Missing, duplicated or
  mismatched project/article/access/agent records make the evidence INVALID.
- Wikimedia daily data is historical and may lag publication. It is never
  described as live.
- Raw response bytes are SHA-256 hashed. Observation hashes cover
  `(date, views, source timestamp)`.
- Pageviews are a proxy for attention. Hashes prove integrity of the recorded
  payload and calculation; they do not prove organic attention or absence of
  manipulation.

## 4. Canonical market rule format

Schema: `notch.market-rule/2`. The rule is an offchain document; the S2 contract
stores only the `rule_hash` in the exact form `sha256:<64 lowercase hex>` that
its `is_valid_digest` function accepts.

Rule hash: SHA-256 over canonical UTF-8 JSON with sorted keys and compact
separators. The hash is **not** a reused S3A proposal ID. It commits to the
market ID, mode, question, choices, source, topics, observation window,
formula/threshold/tie, minimum baseline, invalidation policy, exact market
timing, contract metadata, candidate provenance and calibration report digest.

Trimmed real replay rule (full rule in the evidence bundle):

```json
{
  "schema_version": "notch.market-rule/2",
  "rule_version": "s3b-oracle/1",
  "market_id": "s3b-replay-trend-nvidia-20261103-20261110",
  "mode": "trend_trading",
  "question": "HISTORICAL REPLAY (not a forecast): Will daily en.wikipedia.org pageviews for Nvidia grow by at least 13.50% on the full UTC day 2026-11-10 versus the full UTC day 2026-11-03? ...",
  "choices": ["UP", "DOWN"],
  "source": {"id": "wikimedia-pageviews-v1", "project": "en.wikipedia.org", "access": "all-access", "agent": "user", "metric": "daily_pageviews"},
  "topics": [{"topic_id": "nvidia", "article_title": "Nvidia", "page_id": 39120}],
  "observation": {"baseline_date": "2026-11-03", "target_date": "2026-11-10", "replay": true, "replay_label": "HISTORICAL_REPLAY"},
  "formula": {"version": "growth-threshold-v1", "threshold_bps": 1350, "up_if": "growth_bps >= threshold_bps"},
  "minimum_baseline_views": 1000,
  "invalidation_policy": "refund_on_void",
  "market_timing": {"open_at_ns": "1794452400000000000", "close_at_ns": "1794787140000000000", "resolve_after_ns": "1794916800000000000"},
  "contract": {"network": "testnet", "account": "market.notch-dev.testnet", "collateral_token": "usdc.tidepool-sandbox.testnet"},
  "calibration": {"report_digest": "sha256:5924d37f2f54e571f80d4c788441b126a98ddf10ce3899a7fc5565fb1a1b153e"},
  "governance": {"operator_approval_required": true, "auto_approved": false}
}
```

Validation rejects malformed/missing fields, mismatched replay labels, invalid
threshold/tie ranges, inconsistent ISO/ns timing, past entry close, target after
resolution eligibility, duplicate/conflicting rules for one market ID, and any
attempt to auto-approve.

## 5. Evidence receipt schema

Schema: `notch.oracle.evidence/1`. The receipt contains:

- market ID, frozen rule hash, mode, resolver version;
- exact source query and article identity (page ID);
- baseline and target observations with source timestamps and values;
- retrieval timestamps;
- raw response hashes and per-observation hashes;
- formula, thresholds/tie tolerance, exact calculation inputs;
- outcome and invalidity reason;
- final `evidence_digest` in `sha256:<64 hex>` form accepted by the S2
  `evidence_hash`/`reason_hash` fields.

Digest rule: SHA-256 over canonical UTF-8 JSON of the receipt excluding the
`evidence_digest` field and excluding wall-clock `retrieved_at` metadata. The
retrieval timestamps remain in the receipt for audit but are not immutable
source measurements. This makes the same historical source data reproduce the
same digest on a later fetch; changing any source value, date, article, formula
input, threshold or outcome changes the digest.

Real replay evidence:

| Artifact | Value |
| --- | --- |
| Nvidia replay rule hash | `sha256:1c42a2d04a29c5ba2a0bde3cb8e8a65d06292c965180143022cb07e979c6a47b` |
| Nvidia replay evidence digest | `sha256:0c5ede6be9542b2d161601d6e5e6205c725dc8bf7ad9a488a63911c5f22ddbb2` |
| Nvidia outcome | `UP` (baseline 4,743 → target 123,851; growth 251,123 bps; threshold 1,350) |
| Battle replay rule hash | `sha256:64a41270b9b68a7c33a972001adc1122b35c0877d1e04692f2cf2742fad1c19d` |
| Battle replay evidence digest | `sha256:cef387d5905985f5bf2644d2cb4daad735dfd8b076fc429a598d199927a60e12` |
| Battle outcome | `TOPIC_A` Bitcoin (Bitcoin 1,620 bps, ChatGPT -4,931 bps, difference 6,551, tie tolerance 930) |

All receipts were verified with `verify_evidence`, which recomputes the digest,
recomputes the observation hashes, and re-runs the deterministic outcome from
the stored observations.

The CLI can verify any receipt independently:

```bash
python -m services.oracle verify-evidence <evidence.json>
```

A mutation of a baseline view changes both the digest and observation hash and
is rejected. The tests also verify that recomputing a digest after mutation
still fails the observation-hash check.

## 6. Threshold calibration

Calibration uses 56 complete historical days of one-week growth ending before
the baseline day (no lookahead). Threshold policy `threshold-calibration-v1`:
nearest-rank p75 of historical 7-day growth, clamped to [0, 10,000] bps and
rounded up to 50 bps. Battle tie policy `tie-calibration-v1`: nearest-rank p10
of historical absolute growth differences, clamped to [0, 1,000] bps and rounded
up to 10 bps.

| Calibration | Window | Samples | Suggestion | Digest |
| --- | --- | ---: | --- | --- |
| Future Bitcoin | 2026-09-16..2026-11-10 | 56 | threshold 2,300 bps | `sha256:90a8b59ef76ce8bf6c4c577c3325daf6d03b07f6f7fbadf3fb767475f7690b89` |
| Replay Bitcoin | 2026-09-08..2026-11-02 | 56 | threshold 2,350 bps | `sha256:e132d75a06f07a7415cc85e35f824fe0aa6d295ce01a561fcb8a4ea8bae2dbfb` |
| Replay Nvidia | 2026-09-08..2026-11-02 | 56 | threshold 1,350 bps | `sha256:5924d37f2f54e571f80d4c788441b126a98ddf10ce3899a7fc5565fb1a1b153e` |
| Replay ChatGPT | 2026-09-08..2026-11-02 | 56 | threshold 5,900 bps | `sha256:53c920372d23adbbb517bcca048134265579fb79f4689ef080a9d60f631c6c57` |
| Replay battle BTC/ChatGPT | 2026-09-08..2026-11-02 | 56 | tie 930 bps | `sha256:94c7c624d9e79b074ee0edb5b2ba5d273531fbe04cb7418a73effb0d4afb0dd4` |

The future and replay Bitcoin suggestions differ because their calibration
windows end on different dates (2026-11-10 vs 2026-11-02). The threshold is a
reproducible historical proposal, not a prediction of future returns. Full
reports are embedded in the evidence bundle under `calibration_reports`.

## 7. Candidate validation results

Source: `docs/evidence/s3a_live_scan_20261112.json`.

| Candidate | Measurement | Interest (informational) | Recognizable | Decision |
| --- | --- | --- | --- | --- |
| Bitcoin | VALID | low_but_measurable (3,751 baseline) | yes | READY_FOR_OPERATOR_REVIEW |
| ChatGPT | VALID | high (117,118 baseline) | yes | READY_FOR_OPERATOR_REVIEW |
| Nvidia | VALID | low_but_measurable (4,743 baseline) | yes | READY_FOR_OPERATOR_REVIEW |
| Bitcoin future | PENDING_OBSERVATION | unknown until baseline | yes | READY_FOR_OPERATOR_REVIEW_FUTURE |
| Bitcoin vs ChatGPT | VALID | — | yes | READY_FOR_OPERATOR_REVIEW |
| Nvidia vs Jensen Huang | — | — | — | REJECT_CORRELATED_TOPICS (company/CEO) |

Market interest does not determine measurement validity. A low-interest but
measurable topic remains eligible; the reviewer sees the interest label and
decides. No candidate is automatically approved.

## 8. Proposed market shortlist

All three are **DRAFT**; no market was created.

| # | Name | Mode | Market ID | Rule hash | Observation | Threshold / tie | Evidence |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Future Bitcoin | Trend Trading | `s3b-future-btc-20261116-20261123` | `sha256:cd215ff8e2e09166607b04925464acc086b5c20b058de4fab2e8e07c633b789b` | 2026-11-16 / 2026-11-23 | 2,300 bps | Pending (future window) |
| 2 | Replay Nvidia | Trend Trading | `s3b-replay-trend-nvidia-20261103-20261110` | `sha256:1c42a2d04a29c5ba2a0bde3cb8e8a65d06292c965180143022cb07e979c6a47b` | 2026-11-03 / 2026-11-10 historical | 1,350 bps | `UP`, digest `sha256:0c5ede6b…` |
| 3 | Replay Bitcoin vs ChatGPT | Trend Battle | `s3b-replay-battle-btc-chatgpt-20261103-20261110` | `sha256:64a41270b9b68a7c33a972001adc1122b35c0877d1e04692f2cf2742fad1c19d` | 2026-11-03 / 2026-11-10 historical | tie 930 bps, void | `TOPIC_A` (Bitcoin), digest `sha256:cef387d5…` |

Exact S2 `create_market` payloads are in:

- `docs/evidence/s3b_create_args_future_bitcoin.json`
- `docs/evidence/s3b_create_args_replay_trend_nvidia.json`
- `docs/evidence/s3b_create_args_replay_battle_bitcoin_chatgpt.json`

They validate against the deployed S2 argument shape: two choices, top-level
`source_id`, `rule_hash`, string ns timestamps, `invalidation_policy:
refund_on_void`, and the battle block with shared observation start/end,
`growth_comparison_v1`, minimum baseline and `tie_policy: void`.

## 9. Resolution preparation

The preparation layer reads `get_market`, `get_contract_config` and the chain
time, then checks:

- rule is APPROVED;
- evidence digest and rule hash match;
- evidence is complete and independently valid;
- onchain market ID, mode, source, rule hash, question, choices and timing match
  the frozen rule;
- battle observations/tie policy/minimum baseline match;
- collateral token matches;
- `now >= market.resolve_after` and the market is Open/Closed (or already final);
- winning side has nonzero stake; otherwise it warns and maps to `void_market`.

Outputs are exactly one of:

```text
resolve_market  {"market_id": "...", "winning_outcome": 0|1, "evidence_hash": "sha256:..."}
resolve_tie     {"market_id": "...", "evidence_hash": "sha256:..."}
void_market     {"market_id": "...", "reason_hash": "sha256:..."}
```

Repeated identical preparation is idempotent. A conflicting job for the same
market with different evidence/action is rejected. A blocked plan is returned
with blockers and is not persisted as a prepared job. The plan includes a
near-cli-rs command template with `<resolver-account>`; no private key, seed
phrase or signature is produced or stored.

Current live preparation smoke: the deployed contract has **market_count 0**,
so an onchain preparation is correctly `BLOCKED` with
`ONCHAIN_MARKET_NOT_PROVIDED` and no transaction. The read-only snapshot is in
`docs/evidence/s3b_onchain_read_20261112.json`.

## 10. Reproducibility evidence

The live demo and an offline replay of the same recorded API responses produced
identical:

- rule hashes for all three proposals;
- calibration report digests;
- replay evidence digests and outcomes.

Live source retrieval timestamps differ from the fixture replay timestamps, but
those wall-clock fields are preserved in the receipt and excluded from the
digest. Live raw response hashes and observation hashes match the recorded
fixtures.

Live source ranges (three articles, 71 daily observations each):

| Article | Raw response SHA-256 | Retrieved at |
| --- | --- | --- |
| Bitcoin | `a5f812634989d338a959859e293c4bf51e02bb579a59a39a739a0829ea4226c7` | `2026-11-12T01:07:33Z` |
| ChatGPT | `f3992626c971b8eafc4b661f88a3edbdb712727ec96de97b80b3902463c663e7` | `2026-11-12T01:07:33Z` |
| Nvidia | `f372687814e75ca213ef31e014a2a9a8dc204340f249a44922ae9e1401e436f2` | `2026-11-12T01:07:34Z` |

Bundle: [`docs/evidence/s3b_demo_20261112.json`](evidence/s3b_demo_20261112.json).

Onchain read snapshot at block timestamp `2026-11-12T01:08:50Z`:
collateral `usdc.tidepool-sandbox.testnet`, `market_count: 0`, all three
prepared market IDs return `null`. **No submitted transactions.**

## 11. Tests and verification

```text
$ python -m unittest discover -s services/oracle/tests -t .
Ran 65 tests
OK

$ python -m unittest discover -s services/trend_radar/tests -t .
Ran 76 tests
OK

$ AWS_LC_SYS_PREBUILT_NASM=1 cargo test -p notch-market
running 109 tests
test result: ok. 109 passed; 0 failed; 0 ignored
```

Coverage includes complete/incomplete/missing/duplicate source responses,
wrong article/project/access, raw and observation hashes, canonical calibration,
no-lookahead, low baseline, exact threshold equality, positive/negative/zero
growth, u64 boundaries, battle A/B/tie and tie-boundary, invalid data never a
winner, candidate relationship/alias/parent-child/sensitivity/ambiguity checks,
rule reproducibility, duplicate/conflicting rules, approved-rule immutability,
exact S2 create args, evidence mutation, digest reproducibility, resolution
idempotency/conflicts, tie/void mapping, no-winning-stake handling, replay/future
labeling, CLI demo/verify/approve/prepare/resolve, and no fabricated candidates.

A bounded real-source smoke test fetched all three source ranges live and
produced the bundle above. No live API is used by the automated tests; they use
recorded fixtures.

## 12. Replay-market limitations

- A replay market is a real onchain market whose **observation window is
  historical** and whose outcome is already measurable. It is explicitly labeled
  `HISTORICAL REPLAY (not a forecast)` in the question and in
  `observation.replay_label`.
- Entry, close and resolution eligibility timestamps are future dates on the
  contract, even though the source dates are historical. The contract is not
  told that it is a replay; the frozen rule hash and question carry the label.
- A replay is not evidence of forecasting skill and must not be presented as
  unknown-outcome. The evidence is known before the market opens.
- If source data is incomplete or missing, a replay resolves as INVALID →
  `void_market`, never as a winning outcome.
- A future market has no evidence until its target day passes; it must not be
  resolved early. The current future Bitcoin rule is pending.

## 13. Resolver trust boundary

The S2 contract authorizes a single resolver account. S3B computes evidence and
prepares the exact call, but it does **not** sign or submit. The resolver can
still choose to submit a different outcome or void; the S2 contract cannot
independently verify Wikimedia data or the formula. The evidence digest makes
the proposed result auditable and reproducible, but only proves the integrity
of the recorded payload/calculation, not organic attention or resolver honesty.
A future slice can add multi-party attestations, challenge windows or an
independent onchain verifier.

## 14. Exact S2.5 integration instructions

The old S2.5 rule
`docs/market-rules/forecast-ai-attention-20261114-20261121.json`
(`sha256:a35c5ca6…`, schema `/1`) was frozen before S3B and has no calibration
or S3B-compatible evidence. **Do not silently reuse its hash.** The S2.5 market
is still uncreated. For an AI market, create an S3B rule with a new calibration
and freeze it; otherwise use the S3B future Bitcoin rule.

1. Review the candidate/rule and explicitly approve it locally:

```bash
python -m services.oracle --data-dir var/oracle \
  approve-rule <rule_hash> \
  --reason "operator approval for S2.5 creation" \
  --operator notch-dev.testnet
```

2. Only after that approval, create the market with the exact prepared args
   (this is an S2.5 action, not S3B; **not executed here**):

```bash
near contract call-function as-transaction market.notch-dev.testnet create_market \
  file-args docs/evidence/s3b_create_args_future_bitcoin.json \
  prepaid-gas '100 Tgas' attached-deposit '0 NEAR' \
  sign-as notch-dev.testnet network-config testnet sign-with-keychain send
```

3. Verify with `get_market` and confirm the returned `rule_hash`, question,
   choices, source, open/close/resolve timestamps and battle block exactly match
   the frozen rule.

4. For the future market, wait for the target day and then generate evidence:

```bash
python -m services.oracle --data-dir var/oracle \
  resolve <rule_hash>
```

For replay markets, evidence already exists.

5. Prepare the onchain resolution (read-only):

```bash
python -m services.oracle --data-dir var/oracle \
  prepare-resolution --rule-hash <rule_hash> \
  --evidence-digest <evidence_digest> \
  --onchain \
  --now 2026-11-25T13:00:00Z
```

The plan returns `PREPARED` only when the rule is approved, the onchain
configuration matches, the market is past `resolve_after`, and evidence
verifies. The exact `contract_call` is the authority; the plan's near-cli-rs
template contains a `<resolver-account>` placeholder.

6. Submit only from the configured resolver, outside S3B, after independent
   approval of the prepared plan. Never reuse an evidence digest for a
   different market, and never call `resolve_market` for a tie or invalid
   receipt.

The current onchain state has no market (`market_count: 0`), so the preparation
step is correctly blocked. No transaction was sent.

## 15. Remaining blockers and risks

1. **No S2.5/S3B market exists onchain.** The shortlist rules are DRAFT; market
   creation requires explicit operator approval and a funded signer.
2. **No submission.** S3B deliberately stops at unsigned plans; resolver keys
   are not exposed.
3. **Old S2.5 rule incompatibility.** The pre-S3B schema `/1` rule cannot be
   resolved by S3B without a new rule/evidence path.
4. **Resolver trust.** A resolver can submit a conflicting outcome; the S2
   contract has no independent data verifier.
5. **Source dependency.** Wikimedia lag, missing days, redirects, title changes
   and manipulation can invalidate a market; those cases void, not win.
6. **Calibration is historical.** p75/p10 thresholds are proposals, not
   predictions. S2B/operator review should approve or adjust them.
7. **Battle semantic correlation.** Measurement compatibility is checked; the
   Nvidia/Jensen example is rejected, but a broader semantic relationship graph
   is future work.
8. **Market interest is informational.** Low popularity never rejects a
   measurable topic; editors decide whether it is worth a market.
9. **Replay labels live offchain in the rule/question.** The S2 contract stores
   only the rule hash and question; the evidence bundle must be published with
   the market.
10. **No scheduled oracle worker.** `resolve`/`prepare-resolution` are manual;
    scheduling and alerts are a later slice.

## 16. Files added/changed

Added:

- `services/oracle/` implementation, fixtures and 64 tests
- `docs/S3B_ORACLE_VERIFICATION.md`
- `docs/evidence/s3b_demo_20261112.json`
- `docs/evidence/s3b_onchain_read_20261112.json`
- `docs/evidence/s3b_create_args_*.json`
- `services/oracle/README.md`
- `.github/workflows/oracle.yml`

Changed:

- `README.md` (S3B status, commands, links)
- `.env.example` (oracle data/operator placeholders)
- `.github/workflows/oracle.yml`

Preserved: all S3A source, fixtures and evidence; all S2/S2.5 contract source,
deployment, rules and verification documents. No frontend changes. No contract
redeployment. No token transfers.
