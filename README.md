# Notch

**Evidence-led attention markets.** NEAR-first, testnet-only.

This repository contains **S3A: the backend Trend Radar**, **S3B: the
deterministic attention oracle**, and **S4: a Tidepool/1Click-compatible
testnet funding adapter** on top of the S2 NEAR market contract. The radar finds
and ranks candidates; the oracle calibrates thresholds, freezes versioned rules,
produces canonical evidence digests and prepares S2 resolution calls; the S4
adapter discovers testnet assets, produces dry and live quotes, and generates
exact deposit instructions. The S2.5 short-window replay markets were created,
funded, resolved and claimed on NEAR testnet on 2026-11-12. There is no
frontend, AI component or S5 consumer surface yet. S4 executed an approved
2-test-USDT Tidepool swap and received 1.998769 test USDC.

- Product source of truth: [`docs/Notch_Product_Idea.md`](docs/Notch_Product_Idea.md)
  and [`docs/Notch_PRD_Architecture_Build_Plan.md`](docs/Notch_PRD_Architecture_Build_Plan.md)
- Contract source: [`contracts/market/`](contracts/market)
- Contract interface, collateral and deployment guide:
  [`contracts/market/README.md`](contracts/market/README.md)
- Verification evidence: [`docs/S1_VERIFICATION.md`](docs/S1_VERIFICATION.md),
  [`docs/S2_VERIFICATION.md`](docs/S2_VERIFICATION.md),
  [`docs/S3A_TREND_RADAR_VERIFICATION.md`](docs/S3A_TREND_RADAR_VERIFICATION.md),
  [`docs/S3B_ORACLE_VERIFICATION.md`](docs/S3B_ORACLE_VERIFICATION.md),
  [`docs/S4_INTENTS_VERIFICATION.md`](docs/S4_INTENTS_VERIFICATION.md),
  [`docs/S5_NEAR_AI_VERIFICATION.md`](docs/S5_NEAR_AI_VERIFICATION.md),
  [`docs/S6_WEB_API_VERIFICATION.md`](docs/S6_WEB_API_VERIFICATION.md),
  [`docs/FRONTEND_INTEGRATION_CONTRACT.md`](docs/FRONTEND_INTEGRATION_CONTRACT.md),
  [`docs/S2_5_ONCHAIN_VERIFICATION.md`](docs/S2_5_ONCHAIN_VERIFICATION.md)

## What S2 actually implements

One Rust/NEAR contract, one accounting engine, two binary market modes:

| Capability | Status |
| --- | --- |
| Secure one-time initialization | Implemented and tested |
| Owner / operator / resolver roles | Implemented and tested |
| Configurable, immutable NEP-141 collateral token | Implemented and tested |
| Trend Trading markets with frozen rule hash | Implemented and tested |
| Trend Battle markets with topics, shared observation window, formula, baseline, tie tolerance and tie policy | Implemented and tested |
| Deterministic battle configuration validation | Implemented and tested |
| NEP-141 `ft_on_transfer` entries with refunds on rejection | Implemented and tested on a real sandbox |
| Immutable config, time-windowed entries, global entry pause | Implemented and tested |
| Resolver-authorized winner resolution with evidence digest | Implemented and tested |
| Resolver-only tie → VOID → full refunds | Implemented and tested |
| Shared pooled payouts, zero fees, rounding/dust accounting | Implemented and tested |
| Callback-confirmed claims, retry after failed transfer | Implemented and tested |
| Cross-mode accounting conservation | Implemented and tested |
| Public testnet contract deployment | Deployed and verified; S2.5 replay markets executed 2026-11-12 |
| Trend Radar discovery (S3A) | Implemented and tested; proposals only, no onchain markets |
| Deterministic attention oracle (S3B) | Implemented and tested; rules approved and onchain resolution executed |
| Onchain S3B market creation/resolution | Executed — 2 markets created, resolved and claimed |
| Tidepool/1Click-compatible funding (S4) | Executed: 2 test USDT → 1.998769 test USDC; provider SUCCESS; balance verified |
| NEAR AI Trend Briefs (S5) | Backend implemented; model catalog verified; live inference blocked by missing key; deterministic fallback briefs generated |
| Frontend-ready HTTP API (S6) | Implemented; 17 API tests; live smoke passed; approved future market created |
| Frontend / S5 consumer surface | Not started |

The contract **is deployed to public NEAR testnet** at
`market.notch-dev.testnet` with Tidepool test USDC as collateral. The two S2.5
replay markets (Nvidia Trend Trading and Bitcoin-vs-ChatGPT Trend Battle) were
executed on 2026-11-12 with short 90-minute entry windows: created, funded with
1 test USDC on each winning side, closed, resolved with S3B evidence, and
claimed. The wallet was restored to 100 test USDC. Only the winning side was
funded, so the claims prove collateral recovery and settlement mechanics, not
trading profit; there was no manufactured opposing trader.
Current state, all transaction hashes and evidence:
[`docs/S2_5_ONCHAIN_VERIFICATION.md`](docs/S2_5_ONCHAIN_VERIFICATION.md) section 11
and [`docs/TESTNET_DEPLOYMENT.md`](docs/TESTNET_DEPLOYMENT.md).

## S3A Trend Radar

Backend-only discovery from Wikimedia Pageviews, CoinGecko trending and Hacker
News, with deterministic ranking, eligibility checks and operator-reviewed
PROPOSED drafts. Python standard library only.

```bash
# One bounded live scan
python -m services.trend_radar --data-dir var/trend_radar scan --summary

# Offline replay from recorded real API responses
python -m services.trend_radar --data-dir var/trend_radar_fixture   scan --fixtures services/trend_radar/fixtures --summary

# Review interface
python -m services.trend_radar --data-dir var/trend_radar candidates --summary
python -m services.trend_radar --data-dir var/trend_radar proposals --summary
python -m services.trend_radar --data-dir var/trend_radar review <proposal_id>   --approve --reason "reviewed for S3B"
```

Real scan evidence, source API conditions, ranking, eligibility, tests and the
S3B handoff are in
[`docs/S3A_TREND_RADAR_VERIFICATION.md`](docs/S3A_TREND_RADAR_VERIFICATION.md).

## S3B Deterministic Oracle

Backend-only oracle for Trend Trading and Trend Battles. It calibrates a
historical threshold/tie tolerance, freezes a canonical market rule, produces
replay/future evidence receipts, verifies digests and prepares exact S2
`resolve_market` / `resolve_tie` / `void_market` arguments. It never signs or
submits.

```bash
# Prepare the DRAFT shortlist and replay evidence (recorded fixtures)
python -m services.oracle --data-dir var/oracle   --now 2026-11-12T02:00:00Z --fixtures services/oracle/fixtures   demo --summary

# Live source smoke (Wikimedia; no onchain action)
python -m services.oracle --data-dir var/oracle_live   --now 2026-11-12T02:00:00Z --calibration-end 2026-11-10 demo --summary

# Independently verify a receipt
python -m services.oracle verify-evidence   var/oracle/evidence/<receipt>.json

# Approve a rule and prepare an onchain resolution (read-only until submitted)
python -m services.oracle --data-dir var/oracle approve-rule <rule_hash>   --reason "operator approval" --operator notch-dev.testnet
python -m services.oracle --data-dir var/oracle prepare-resolution   --rule-hash <rule_hash> --evidence-digest <digest> --onchain
```

Real calibration, rule hashes, evidence digests, onchain-read status and exact
S2.5 integration steps are in
[`docs/S3B_ORACLE_VERIFICATION.md`](docs/S3B_ORACLE_VERIFICATION.md).

## S4 Intents funding

Backend-only adapter for the community-operated Tidepool 1Click-compatible
testnet sandbox. It reads live `/v0/tokens`, requests dry and live quotes,
generates exact NEAR deposit instructions for `ORIGIN_CHAIN` and `INTENTS`, and
persists a bounded funding state machine. The adapter itself never signs or
broadcasts; the operator executed the approved S4.1 transfer with near-cli.

```bash
python -m services.intents tokens
python -m services.intents routes
python -m services.intents dry-quote \
  --source-asset nep141:usdt.tidepool-sandbox.testnet \
  --amount 2000000 --recipient notch-dev.testnet --deposit-type INTENTS
python -m services.intents prepare-swap \
  --source-asset nep141:usdt.tidepool-sandbox.testnet \
  --amount 2000000 --recipient notch-dev.testnet --deposit-type INTENTS
python -m services.intents funding --account notch-dev.testnet
```

The approved S4.1 swap moved **2 test USDT** to Tidepool on 2026-11-12. Deposit
tx `E4125h7BZDbubswjLr2mmM4BfVpxtVVGZ1Qmcq9beuq2` succeeded, Tidepool returned
`SUCCESS`, settlement tx `2C9xGtKeMDfBvwdZwEAnkPAg2DRXGAPnggursmHWBY8N` completed,
and the wallet received **1.998769 test USDC**. No market entry was submitted.
Evidence and exact transaction details are in
[`docs/S4_INTENTS_VERIFICATION.md`](docs/S4_INTENTS_VERIFICATION.md) section 14.
Test tokens have no value; never send real assets to Tidepool.

## S5 NEAR AI trend briefs

Backend-only, evidence-grounded briefs for Radar candidates and frozen S3B
markets. The service builds prompts only from stored S3A candidates and S3B
rules/evidence, validates every numeric claim against supplied measurements,
and never changes a rule or outcome. It never signs or submits a transaction.

```bash
python -m services.near_ai status
python -m services.near_ai radar-brief --candidate-id cand_b279c92126deeecb4beb
python -m services.near_ai radar-brief --candidate-id cand_9118da9248a28ca00f02
python -m services.near_ai market-brief --market-id s3b-replay-trend-nvidia-20261103-20261110
python -m unittest discover -s services/near_ai/tests -t .
```

No `NEAR_AI_KEY` is configured in this environment, so live inference is not
claimed. The generated Nvidia/Bitcoin Radar briefs and Nvidia historical-replay
market brief are labeled `NON_AI_FALLBACK`, provider `deterministic`, model
`none`. The selected model `z-ai/glm-5.3-flash` was verified in the live NEAR AI
catalog. See [`docs/S5_NEAR_AI_VERIFICATION.md`](docs/S5_NEAR_AI_VERIFICATION.md).

## S6 frontend-ready web API

A small stdlib HTTP API over the existing services. It serves real Radar
candidates, actual onchain markets, verified S3B evidence, cached/deterministic
briefs, Tidepool funding quotes/status, wallet balances/positions and unsigned
market-entry instructions. It never signs or broadcasts.

```bash
python -m services.web_api --host 127.0.0.1 --port 8000
python scripts/s6_live_smoke.py
python -m unittest discover -s services/web_api/tests -t .
```

Live smoke served three actual markets (two resolved historical replays plus the
approved open future market), 11 eligible Radar candidates, verified S3B
evidence, a deterministic Nvidia market brief, 101.998769 test USDC, two claimed
positions and 31 Tidepool tokens. Entry preparation correctly rejected a resolved
market with 409 and returned an unsigned intent for the open future market. See
[`docs/S6_WEB_API_VERIFICATION.md`](docs/S6_WEB_API_VERIFICATION.md) and
[`docs/FRONTEND_INTEGRATION_CONTRACT.md`](docs/FRONTEND_INTEGRATION_CONTRACT.md).

## Verify locally

```bash
# Rust 1.96.0, near-sdk 5.30.1
rustup target add wasm32-unknown-unknown

cargo test -p notch-market                     # 109 unit tests
cargo build --release --target wasm32-unknown-unknown -p notch-market
sha256sum target/wasm32-unknown-unknown/release/notch_market.wasm

# Python 3.11+ stdlib; no pip dependencies
python -m unittest discover -s services/trend_radar/tests -t .
python -m unittest discover -s services/oracle/tests -t .
python -m unittest discover -s services/intents/tests -t .
python -m unittest discover -s services/near_ai/tests -t .
python -m unittest discover -s services/web_api/tests -t .
```

Windows only: the near-sdk `unit-testing` feature pulls `aws-lc-sys`, which
needs NASM. Either install NASM or set `AWS_LC_SYS_PREBUILT_NASM=1` before
running tests.

Built artifact:
`contracts/market/res/notch_market.wasm` — 451,574 bytes,
`sha256:9892eaa0c113378ca188137d6565d444ff6a8794bda3a596ce1fdcbb692f0f08`.

### Real-sandbox integration tests

`near-workspaces` supports Linux x86_64/aarch64 and macOS arm64. On Windows, run
the tests inside WSL Ubuntu:

```bash
# build test artifacts
cargo build --release --target wasm32-unknown-unknown -p notch-market
mkdir -p contracts/market/res
cp target/wasm32-unknown-unknown/release/notch_market.wasm contracts/market/res/notch_market.wasm
(cd tests/test-token && cargo build --release --target wasm32-unknown-unknown)

# run the cross-contract suite (deploys a real NEP-141 token + the market)
cd tests/integration && cargo test --test market_flow -- --nocapture
```

Three sandbox tests cover Trend Trading end-to-end, void/refund + failed-FT
recovery, and Trend Battles: winner payout, tie → VOID → refunds, duplicate
claims and immutable final states.

## Repository layout

```text
contracts/market/          Rust NEAR market contract (S2)
  res/notch_market.wasm    Built artifact (451,574 bytes)
  src/                     contract, battle types, math, unit tests
services/trend_radar/      S3A discovery service, fixtures and tests (Python stdlib)
services/oracle/           S3B deterministic oracle, fixtures and tests
services/intents/          S4 Tidepool testnet funding adapter, fixtures and tests
services/near_ai/          S5 evidence-grounded NEAR AI briefs, fixtures and tests
services/web_api/          S6 frontend-ready HTTP API, schemas, tests and smoke script
docs/                      Product source of truth + S1–S6 evidence
tests/test-token/          Minimal NEP-141 token, test infrastructure only
tests/integration/         near-workspaces end-to-end tests
.github/workflows/         Unit-test + WASM build + sandbox integration CI path
```

## Testnet collateral

The collateral is Tidepool test USDC: `usdc.tidepool-sandbox.testnet` (NEP-141,
6 decimals, 0.00125 NEAR storage registration). Both the market contract and
`notch-dev.testnet` are registered with the token. The development wallet holds
**101.998769 test USDC** and **98 test USDT**, plus small test wNEAR/wBTC/ETH/XAUT
balances. S4 executed an approved 2 test USDT → test USDC swap. Test assets have
no value. Raw collateral evidence is in
[`docs/s2_collateral_check.txt`](docs/s2_collateral_check.txt); current wallet
and market state is in
[`docs/TESTNET_DEPLOYMENT.md`](docs/TESTNET_DEPLOYMENT.md).

## Scope boundaries

- NEAR testnet only. No mainnet assets, no real funds.
- No leverage, fees, liquidation, secondary trading or partial refunds.
- S3B computes deterministic outcomes and evidence digests, but resolution is
  still submitted by the S2 resolver. The digest proves integrity of the
  recorded source payload/calculation, not organic attention or resolver
  honesty. Both S2.5 markets were resolved and claimed on testnet.
- S4 is a quote/deposit-instruction adapter. The operator executed the approved
  funding transfer; the backend never signs. Market entry remains separate.
- The collateral token is configured once at initialization and never changes.
- S2 requires a fresh deployment; S1 contract state is not migrated.
