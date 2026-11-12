# S3A — Trend Radar & Market Discovery verification

Date: 2026-11-12 (UTC)
Status:

- **S3A implementation complete and verified locally: YES**
- **Real public-source discovery scan executed: YES**
- **Onchain market created: NO** — S3A never creates markets, and S2.5 remains
  at its explicit approval gate
- **S3B resolver implemented: NO** — this document defines the handoff

## 1. Scope

S3A is a backend discovery system. It:

- retrieves signals from three free public sources;
- normalizes and conservatively deduplicates topics;
- produces deterministic discovery rankings;
- independently evaluates whether a candidate can be measured and settled;
- generates **PROPOSED** Trend Trading and Trend Battle drafts;
- persists operator approval/rejection decisions;
- exposes a typed service interface and CLI.

It does **not** create onchain markets, sign transactions, transfer tokens,
produce final settlement evidence, or modify the S2 contract. CoinGecko and
Hacker News are discovery-only; Wikimedia Pageviews is the only candidate
settlement source.

## 2. Architecture

```text
Wikimedia Pageviews ─┐
MediaWiki identity ──┤
CoinGecko trending ──┼─> source adapters ─> normalized observations
Hacker News Algolia ─┘                           │
                                                 ▼
                                     conservative deduplication
                                                 │
                                                 ▼
                                  deterministic discovery ranking
                                                 │
                              bounded Wikimedia coverage probes
                                                 │
                                                 ▼
                                eligibility + PROPOSED market drafts
                                                 │
                                                 ▼
                                    SQLite candidates, proposals,
                                    decisions, snapshots and health
                                                 │
                                    CLI + TrendRadarService interface
```

Repository layout:

```text
services/trend_radar/
  models.py          versioned candidate/proposal/scan/coverage types
  canonical.py       stable IDs, curated aliases, category inference
  http.py            live HTTP, cache, retries, rate limiting, fixtures
  dedupe.py          normalization and conservative merging
  ranking.py         radar-score/1
  eligibility.py     market-readiness evaluation and battle compatibility
  proposals.py       PROPOSED trend/battle drafts
  store.py           SQLite persistence, decisions, scan deduplication
  service.py         ScanConfig + TrendRadarService orchestration
  cli.py / __main__.py
  sources/           wikimedia.py, coingecko.py, hackernews.py
  fixtures/          recorded real API responses + replay manifest
  tests/             76 unittest tests
```

No third-party Python packages are required; only the standard library.

## 3. Sources, access and rate limits

### 3.1 Wikimedia Pageviews + MediaWiki

- Top articles:
  `https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia.org/all-access/{YYYY}/{MM}/{DD}`
- Per-article daily pageviews:
  `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/{article}/daily/{start}/{end}`
- Identity/redirects:
  `https://en.wikipedia.org/w/api.php?action=query&redirects=1&prop=info|pageprops...`
- Authentication: none. An identified User-Agent is sent. The default is
  `NotchTrendRadar/0.1 (NEAR testnet discovery; local development)`; override
  with `RADAR_USER_AGENT`.
- Complete reporting periods only: the adapter tries yesterday and up to two
  preceding complete UTC days. The response's own `year/month/day` is stored.
  No claim is made that daily pageviews are live.
- Non-topic pages are filtered: `Main Page`, namespace prefixes
  (`Special:`, `Wikipedia:`, `Portal:`, `Help:`, `File:`, `Category:`,
  `Template:`, `Talk:`, `User:`, `Draft:`, `Module:`, `MediaWiki:`, `Book:`,
  `TimedText:`, `Gadget:`), list/death/timeline/index/outline/glossary pages,
  and disambiguation titles.
- Cache TTL: 6 hours. Minimum request interval: 0.2 s.
- Rate-limit behaviour: 429 is retried with `Retry-After` when ≤5 s, otherwise
  the request stops and cached data may be used. Max 2 retries; 12 s timeout.
- Data is CC0; source attribution is preserved in each evidence record.

### 3.2 CoinGecko

- Endpoint: `https://api.coingecko.com/api/v3/search/trending`
- Authentication: none in the live scan. An optional free Demo API key can be
  supplied through `COINGECKO_DEMO_API_KEY` and is sent as
  `x-cg-demo-api-key`; it is never logged, stored in the DB or committed.
- Preserved per coin: stable coin `id`, symbol, name, market-cap rank,
  trending rank, source URL and fetch timestamp.
- Trending categories (currently six) are preserved as source context; they are
  **not** candidates and are **not** treated as attention or prices.
- Price and market-cap movement are never used as attention signals or
  settlement metrics. Only the trending rank/order contributes to discovery
  prominence.
- Cache TTL: 5 minutes. Minimum request interval: 1 s.
- A CoinGecko failure is isolated: Wikimedia and Hacker News continue.

### 3.3 Hacker News (Algolia)

- Endpoint: `https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30`
- Authentication: none.
- Preserved per story: story `objectID`, title, points, comment count,
  `created_at_i`, HN item URL, story URL and fetch timestamp.
- `Ask HN`, `Show HN`, `Tell HN`, `Launch HN` posts are skipped as discussion or
  product posts; records missing a story ID/title are skipped.
- Cache TTL: 3 minutes. Minimum request interval: 0.2 s.
- Algolia front-page index can lag the live HN page; `max_story_age_seconds` is
  reported in source context.

## 4. Normalized candidate schema

Version: `notch.trend-radar.candidate/1`.

| Field | Meaning |
| --- | --- |
| `candidate_id` | Stable hash of the canonical topic ID (`cand_` + 20 hex) |
| `canonical_topic_id` | `entity:<key>`, `wiki:en.wikipedia.org:<slug>`, `coingecko:coin:<id>`, or `hn:topic:<slug>` |
| `title` | Canonical display title |
| `category` | `Crypto & Web3`, `AI & Technology`, `Gaming & Entertainment`, `Pop Culture & People`, `News & Current Events`, `Other` |
| `aliases` | Curated entity aliases plus source titles, symbols and IDs |
| `source_identities` | Every source-specific identity and identifier (Unix, page ID, story ID, coin ID, URLs) |
| `discovery_evidence` | Raw source observations with metrics, timestamps, URLs, raw response hash/ref |
| `source_urls` | Direct source links |
| `first_seen_at` / `last_seen_at` | When the radar first/last observed the candidate |
| `observed_at` | Newest source observation timestamp |
| `discovery_signals` | Source count, prominence detail, radar score and components, coverage source, measurement signature |
| `eligibility_status` | `ELIGIBLE`, `NEEDS_REVIEW`, `NOT_MEASURABLE`, `STALE`, `REJECTED` |
| `eligibility_reasons` | Stable reason codes (e.g. `no_settlement_coverage`) |
| `confidence` / `reliability` | Discovery confidence/reliability, not a price or odds |
| `proposed_market_modes` | `trend_trading` and/or `trend_battle` on eligible candidates |
| `settlement_coverage` | Wikimedia article/page ID, 7-day daily views and eligibility probe status |

Actual Nvidia candidate excerpt from the live scan:

```json
{
  "candidate_id": "cand_b279c92126deeecb4beb",
  "canonical_topic_id": "entity:nvidia",
  "title": "Nvidia",
  "category": "AI & Technology",
  "source_identities": [
    {
      "source": "wikimedia",
      "article_resolved": "Nvidia",
      "page_id": 39120,
      "url": "https://en.wikipedia.org/wiki/Nvidia"
    },
    {
      "source": "hackernews",
      "story_id": "50459703",
      "url": "https://news.ycombinator.com/item?id=50459703"
    }
  ],
  "discovery_signals": {
    "source_count": 2,
    "sources": ["wikimedia", "hackernews"],
    "settlement_article": "Nvidia",
    "settlement_page_id": 39120,
    "score": 85,
    "score_components": {
      "confirmations": 10,
      "prominence": 20,
      "recency": 20,
      "settlement_coverage": 25,
      "freshness": 5,
      "category_relevance": 5
    }
  },
  "eligibility_status": "ELIGIBLE",
  "eligibility_reasons": ["eligible_settlement_coverage"],
  "proposed_market_modes": ["trend_trading", "trend_battle"]
}
```

Full source identities, evidence hashes and links for the top 12 candidates are
in [`docs/evidence/s3a_live_scan_20261112.json`](evidence/s3a_live_scan_20261112.json).

## 5. Deduplication

The radar uses **curated entity aliases and exact source identities**, never
fuzzy title similarity. The curated table currently covers Bitcoin/BTC,
Ethereum/ETH, Solana, Dogecoin/Doge, Zcash/ZEC, ChatGPT, OpenAI, Artificial
intelligence, and Nvidia/NVDA.

Examples verified by tests:

- `Bitcoin` (Wikimedia) + `BTC` (CoinGecko) + `Bitcoin hits a new high` (HN)
  merge to one `entity:bitcoin` candidate with all three source identities.
- `ChatGPT` + `OpenAI ChatGPT launch` merge to `entity:chatgpt`, while
  `OpenAI valuation` remains a separate `entity:openai` candidate.
- `Apple event announced` and `Apple Inc. earnings` remain separate HN topics;
  no merge based on the shared word "Apple".
- Two HN stories with the same normalized title merge while both story IDs are
  preserved in `discovery_evidence`.
- A wiki article without a curated alias (e.g. `Ramayana: Part 1`) stays
  source-specific instead of being forced into an entity.

Alias conflicts are rejected at import/test time
(`AliasConflictError`); unknown sources are not merged just because their names
look similar.

## 6. Discovery ranking (`radar-score/1`)

The score is a deterministic discovery aid, **not** an attention index, price,
odds or settlement input.

| Component | Max | Rule |
| --- | ---: | --- |
| Confirmations | 20 | 10 per additional independent source (1 source = 0, 2 = 10, 3 = 20) |
| Prominence | 25 | Max of Wikimedia rank, CoinGecko trending rank, HN points |
| Recency | 20 | ≤24 h = 20, ≤48 h = 12, ≤72 h = 6, older = 0 |
| Settlement coverage | 25 | Measurable Wikimedia probe = 25; article known but unprobed = 12; none = 0 |
| Freshness | 5 | All contributing sources fresh; stale/failed = 0 |
| Category relevance | 5 | Category is not `Other` |

Prominence bands:

- Wikimedia rank: 1–10 = 25, 11–50 = 20, 51–200 = 12, otherwise 5.
- CoinGecko trending rank: 1–3 = 25, 4–10 = 18, otherwise 10.
- HN points: ≥500 = 25, ≥200 = 20, ≥100 = 12, otherwise 5.

The score is capped at 100. Sorting is by score descending, then
`candidate_id` ascending. The same inputs always produce the same order; tests
shuffle inputs and re-run. There is no entity-specific or brand-specific boost.

Nvidia live example: 2 sources (10) + Wikimedia rank 17 (20) + 24 h recency
window (20) + coverage (25) + freshness (5) + category relevance (5) = **85**.

## 7. Eligibility

An interesting topic is not automatically a market.

| Status | Meaning |
| --- | --- |
| `ELIGIBLE` | Exact Wikimedia coverage, complete 7-day probe, minimum baseline met, unambiguous topic |
| `NEEDS_REVIEW` | Potential coverage but probe not run, incomplete/failed probe, baseline below minimum, or ambiguous topic |
| `NOT_MEASURABLE` | No Wikimedia settlement article or no pageviews data |
| `STALE` | Observations/sources too old; cached discovery data is not a new measurement |
| `REJECTED` | Invalid source record |

Eligibility checks:

1. A single unambiguous topic and preserved source identity.
2. A supported, independent measurement source (Wikimedia Pageviews only).
3. Historical observations retrievable for a 7-day window.
4. Baseline can meet the configured minimum (1,000 daily views).
5. The article identity resolves to a Wikimedia page ID when available.
6. A fixed observation window can be proposed.
7. The calculation is deterministic and the source is sufficiently reliable.
8. Known manipulation/settlement risks are included in proposal limitations.

The coverage probe is bounded to **12 candidates per scan**, chosen by
preliminary radar score. Candidates beyond that limit are explicitly
`NEEDS_REVIEW` with `coverage_probe_not_run`; they are not marked eligible. No
article match is invented: a curated entity either resolves through MediaWiki
or the candidate stays `NOT_MEASURABLE`.

## 8. Market proposal drafts

Every proposal is `PROPOSED`. No rule hash is finalized and no threshold is
claimed valid. The S3B milestone must freeze and independently reproduce the
rule and evidence before any market creation.

### Trend Trading draft

- Topic, `PROPOSED` question, Wikimedia article/project/access/agent/metric.
- Suggested observation window: baseline = scan date + 3 days, target =
  baseline + 7 days, resolution eligible = target + 2 days.
- Suggested threshold: 1,500 bps (15.00%), marked
  `threshold_status: UNVALIDATED_PROPOSAL`.
- Measurement limitations: daily data lag, bot/spike risk, redirects/title
  changes, pageviews as proxy, S3B rule freeze requirement.

### Trend Battle draft

- Only for two `ELIGIBLE` candidates with the same measurement signature
  (same source, project, access, agent, metric) and distinct articles.
- Comparison formula: `growth_comparison_v1`; tie tolerance: 50 bps; tie
  policy: `void`.
- Same observation window proposal.
- At most five battle drafts per scan among the top six eligible candidates.

Trend drafts are capped at 10 per scan. Additional eligible candidates remain
discoverable and eligible but do not receive a draft until an operator or a
later slice selects them; the cap is not a hidden eligibility decision.

Operator approval is a review decision only. It does not create a market.

## 9. Operator review

SQLite persistence at `RADAR_DATA_DIR/radar.sqlite3` stores:

- scan runs and deduplication fingerprints;
- last successful source snapshots;
- source health;
- candidates;
- proposals;
- an append-only decision history.

```bash
python -m services.trend_radar --data-dir var/trend_radar candidates --summary
python -m services.trend_radar --data-dir var/trend_radar show <candidate_id>
python -m services.trend_radar --data-dir var/trend_radar proposals --summary
python -m services.trend_radar --data-dir var/trend_radar review <proposal_id> \
  --approve --reason "reviewed for S3B"
```

A reason is required. Decisions persist across rescans when the proposal ID is
unchanged. Approval is **not** financial execution and does **not** call the
NEAR contract. Operator identity is a local label (`RADAR_OPERATOR`), not an
authentication system in this slice.

## 10. Failure and resilience behaviour

- HTTP timeout: 12 s; up to two retries for 5xx/network errors.
- 429: `Retry-After` is honoured up to 5 s; otherwise the source is marked
  rate-limited.
- Fresh cache short-circuits live calls (`CACHED` health).
- Failed live calls can fall back to the last cached response (`stale=true`,
  `DEGRADED` health). Stale observations never become new measurements and
  candidates built only from stale sources are `STALE`, never `ELIGIBLE`.
- Each adapter is isolated: CoinGecko failure does not stop Wikimedia or HN.
- If every provider fails and there is no cache, the scan completes with zero
  candidates and failed health; no candidates are invented.
- Last successful snapshots remain in SQLite after a provider failure.
- Duplicate scans with the same source set/config/scan date within 10 minutes
  return the stored result (`deduplicated=true`); a running scan is rejected.
- Source health reports last success, cache use, stale/rate-limit flags and
  item counts.

## 11. CLI and service interface

The CLI is the thin operator surface:

```bash
# One live bounded scan (writes last_scan.json + SQLite)
python -m services.trend_radar --data-dir var/trend_radar scan --summary

# Offline replay from recorded fixtures
python -m services.trend_radar --data-dir var/trend_radar_replay \
  scan --fixtures services/trend_radar/fixtures --summary

# Machine-readable full scan result
python -m services.trend_radar --data-dir var/trend_radar scan
```

`TrendRadarService` exposes typed methods for the future web app:
`scan()`, `list_candidates()`, `get_candidate()`, `list_proposals()`,
`get_proposal()`, `review_proposal()`, `source_health()` and
`last_successful_update()`.

No scheduled process is installed.

## 12. Real live scan evidence

Command:

```bash
python -m services.trend_radar --data-dir var/trend_radar_live_final2 scan --summary
```

Scan: `scan_39fb5a36cdaf619d9fce`
Date: 2026-11-12 UTC
Started/completed: `2026-11-12T00:23:57Z` / `2026-11-12T00:24:09Z`
Last successful source update: `2026-11-12T00:24:01Z`
Result: **80 candidates**, **11 ELIGIBLE**, **33 NEEDS_REVIEW**,
**36 NOT_MEASURABLE**, **15 PROPOSED drafts** (10 trend, 5 battle), no errors.

Source health:

| Source | Status | Items | Last success | Cache/stale |
| --- | --- | ---: | --- | --- |
| Wikimedia | ok | 40 | `2026-11-12T00:23:59Z` | no / no |
| CoinGecko | ok | 15 | `2026-11-12T00:24:00Z` | no / no |
| Hacker News | ok | 27 | `2026-11-12T00:24:01Z` | no / no |

Coverage probes: 12 attempted; 11 `ok`, 1 `insufficient_baseline` (Zcash).
The Wikimedia top data is the complete 2026-11-10 reporting day; it is not
presented as a live feed.

Top 12 actual candidates (full evidence and source URLs in the linked JSON):

| # | Candidate | Category | Score | Status | Sources | Primary links |
| ---: | --- | --- | ---: | --- | --- | --- |
| 1 | Nvidia | AI & Technology | 85 | ELIGIBLE | Wikimedia + Hacker News | [Wikipedia](https://en.wikipedia.org/wiki/Nvidia), [HN](https://news.ycombinator.com/item?id=50459703) |
| 2 | Bitcoin | Crypto & Web3 | 73 | ELIGIBLE | CoinGecko | [CoinGecko](https://www.coingecko.com/en/coins/bitcoin), [coverage](https://en.wikipedia.org/wiki/Bitcoin) |
| 3 | Jensen Huang | Other | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/Jensen_Huang) |
| 4 | Russell Brand | Other | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/Russell_Brand) |
| 5 | SS Edmund Fitzgerald | Other | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/SS_Edmund_Fitzgerald) |
| 6 | ChatGPT | AI & Technology | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/ChatGPT) |
| 7 | David Walliams | Other | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/David_Walliams) |
| 8 | .xxx | Other | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/.xxx) |
| 9 | Zcash | Crypto & Web3 | 67 | NEEDS_REVIEW | CoinGecko | [CoinGecko](https://www.coingecko.com/en/coins/zcash), [coverage](https://en.wikipedia.org/wiki/Zcash) |
| 10 | Scene (2026 film) | Gaming & Entertainment | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/Scene_(2026_film)) |
| 11 | Ramayana: Part 1 | Other | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/Ramayana%3A_Part_1) |
| 12 | 2026 United States elections | News & Current Events | 67 | ELIGIBLE | Wikimedia | [Wikipedia](https://en.wikipedia.org/wiki/2026_United_States_elections) |

Actual source observations for the top candidates include:

- Nvidia: Wikimedia 123,851 views on 2026-11-10 (rank 17); HN story
  `50459703` with 338 points / 314 comments; a second HN story `50459776`
  with 160 points; coverage probe passed.
- Bitcoin: CoinGecko trending rank 4, symbol `BTC`, market-cap rank 1; exact
  Wikipedia article coverage probe passed.
- ChatGPT: Wikimedia 59,377 views on 2026-11-10 (rank 44); coverage probe
  passed.
- Zcash: coverage probe returned a baseline below the 1,000-view minimum, so it
  is correctly held at NEEDS_REVIEW rather than market-ready.

Representative proposals:

```text
PROPOSED trend_trading prop_3f9faab70cebeba7d87c Nvidia
PROPOSED trend_trading prop_a8af34451aa43e7b131f Bitcoin
PROPOSED trend_trading prop_fae884f9843643b8a16e ChatGPT
PROPOSED trend_battle  prop_b14fbe6a7e90c00afde3 Nvidia vs Bitcoin
PROPOSED trend_battle  prop_05bb8eb0e45441d15546 Nvidia vs ChatGPT
```

Proposal observation window suggestion: baseline 2026-11-15, target 2026-11-22,
resolve after 2026-11-24T12:00:00Z. Threshold 1,500 bps is explicitly
unvalidated; no rule hash is committed.

Evidence bundle:
[`docs/evidence/s3a_live_scan_20261112.json`](evidence/s3a_live_scan_20261112.json).

The listed titles are discovery results, not endorsements. In particular, the
radar proposed `Nvidia vs Jensen Huang` because both have compatible pageview
measurements; Jensen Huang is Nvidia's CEO, so this pair is semantically
correlated. It is a deliberate example of why operator review is mandatory and
why S3B should add relationship checks.

## 13. Tests and verification

```text
$ python -m unittest discover -s services/trend_radar/tests -t .
Ran 76 tests in ~6 s
OK
```

| Area | Tests |
| --- | --- |
| Canonical IDs, aliases, conflict detection, categories | `test_canonical.py` |
| Bitcoin/BTC/CoinGecko/HN merge, ChatGPT/OpenAI, no Apple false merge, source identity preservation | `test_dedupe.py` |
| Ranking components, determinism, tie-break, no brand boost, HN max points | `test_ranking.py` |
| All eligibility statuses, missing coverage, battle compatibility | `test_eligibility.py` |
| PROPOSED trend/battle drafts, incompatible measurements, limits | `test_proposals.py` |
| Timeouts/retries, 429, cache stale fallback, invalid JSON, fixture loaders | `test_http.py` |
| Wikimedia filtering/redirects/pageviews, CoinGecko, HN, provider failures | `test_sources.py` |
| Scan deduplication, snapshots, health retention, decisions | `test_store.py` |
| Full fixture scan, replay determinism, partial/all failure, stale cache, probe limit, decision persistence | `test_service.py` |
| CLI scan/candidates/proposals/review, dedupe, error paths | `test_cli.py` |

Existing S1/S2 contract tests remain unaffected and passing:

```text
$ AWS_LC_SYS_PREBUILT_NASM=1 cargo test -p notch-market
running 109 tests
test result: ok. 109 passed; 0 failed; 0 ignored
```

No contract source, build artifact, deployment or token state was modified.

## 14. API references

- Wikimedia Analytics API:
  <https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/getting-started.html>
- Wikimedia access policy:
  <https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html>
- MediaWiki Action API:
  <https://www.mediawiki.org/wiki/API:Query>
- CoinGecko API documentation:
  <https://docs.coingecko.com/>
- Hacker News API / Algolia search:
  <https://github.com/HackerNews/API> and <https://hn.algolia.com/api>

All access is through documented public APIs with an identified User-Agent.
No access-control bypass, scraping workaround or paid provider is used.

## 15. Known limitations

1. **Discovery score is not attention truth.** It is a transparent radar aid,
   not an attention index, price, probability or settlement metric.
2. **Battle drafts are measurement-compatible, not semantically vetted.**
   Correlated pairs such as Nvidia vs Jensen Huang can appear and must be
   rejected in operator review. S3B should add entity-relationship checks.
3. **Coverage probes are bounded to 12 per scan.** Other wiki candidates are
   `NEEDS_REVIEW`, not silently approved.
4. **Category inference is heuristic.** Many people/ship/list topics land in
   `Other`; the radar does not invent a category it cannot support.
5. **Wikimedia daily data lags.** The latest complete reporting day is used and
   recorded; it is not described as live.
6. **Pageviews are a proxy.** Bots, spikes, redirects and title changes can
   distort attention. Proposals include these limitations.
7. **CoinGecko and HN are discovery-only.** Price/market-cap movement is not
   social attention; HN points/comments are discussion signals.
8. **No operator authentication.** The CLI is backend-only; `RADAR_OPERATOR` is
   a label, not an auth system.
9. **SQLite is single-node local storage.** No multi-user API auth, scheduling
   or alerting exists in S3A.
10. **First-seen is radar first observation**, not the topic's first appearance
    on the internet.
11. **No onchain market was created.** S2.5 remains at its approval gate.

## 16. S3B handoff requirements

1. **Freeze rules for approved proposals.** Use the S2/S2.5 canonical rule
   approach (`scripts/canonical_json_hash.py`): source query, article, full UTC
   days, formula version, threshold/tie tolerance, observation window,
   invalidation policy. Commit the exact `rule_hash` to a market only after
   operator approval.
2. **Threshold calibration.** Validate the proposed 1,500 bps threshold against
   historical volatility, minimum baseline and tie tolerance. Replace the
   `UNVALIDATED_PROPOSAL` status with a reproducible calibration artifact.
3. **Deterministic evidence.** Implement the S3 oracle/evidence pipeline for
   trend and battle calculations, canonical JSON, SHA-256 digest, raw-response
   hashes and resolver version. Map winners to `resolve_market` and ties to
   `resolve_tie` on the existing S2 contract.
4. **Semantic battle vetting.** Add entity-relationship checks so correlated
   topics (company/CEO, same entity under aliases, parent/child concepts) are
   not proposed as battles.
5. **Evidence verification.** Publish a command/endpoint that recomputes the
   digest from stored inputs and links it to the onchain `evidence_hash`.
6. **Operator workflow hardening.** Add authenticated review, decision export,
   scheduling and source-health alerts.
7. **Testnet execution.** The first market and any radar-approved market still
   require explicit operator approval; S3A did not create or fund a market.

## 17. Files added/changed

Added:

- `services/__init__.py`
- `services/trend_radar/` (all modules, sources, fixtures, tests, README)
- `docs/S3A_TREND_RADAR_VERIFICATION.md`
- `docs/evidence/s3a_live_scan_20261112.json`
- `.env.example`
- `.github/workflows/trend-radar.yml` (unit tests + recorded-fixture replay)

Changed:

- `.gitignore` (ignore `var/`, allow `.env.example`)
- `README.md` (S3A status, commands, layout)

Preserved:

- All contract source, S2 artifact, tests and deployment state.
- `docs/Notch_*` product documents, `docs/S1_VERIFICATION.md`,
  `docs/S2_VERIFICATION.md`, `docs/TESTNET_DEPLOYMENT.md`, and the S2.5 market
  rule files were not modified.
