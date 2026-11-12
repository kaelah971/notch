# Recorded fixtures

These are trimmed responses from the real public APIs, used only by the
automated tests. They are not synthetic market data.

| File | Source | Captured from |
| --- | --- | --- |
| `test_wikimedia_top.json` | Wikimedia Pageviews top endpoint | `en.wikipedia.org`, 2026-11-10 daily top articles |
| `test_mediawiki_query.json` | MediaWiki Action API | identity/page-id query for curated titles |
| `test_pageviews_*.json` | Wikimedia Pageviews per-article | 2026-11-03..2026-11-10 daily observations |
| `test_coingecko_trending.json` | CoinGecko `/api/v3/search/trending` | trending coins + categories |
| `test_hackernews_front.json` | HN Algolia `/api/v1/search?tags=front_page` | real front-page hits |

`manifest.json` fixes the replay clock at `2026-11-11T23:45:00Z` and maps API
endpoints to files. Pageviews fixtures exist for Nvidia, ChatGPT,
Artificial_intelligence and Bitcoin. A missing pageviews fixture deliberately
exercises the "no settlement coverage" path (Solana/Zcash in this fixture).

The live scan evidence in `docs/evidence/s3a_live_scan_20261112.json` was
produced separately with the real APIs and is not generated from these fixtures.
