# Oracle fixtures

Recorded real Wikimedia responses used by the S3B automated tests and offline
demo. They are not synthetic data.

| File | Source / range |
| --- | --- |
| `pageviews_Bitcoin.json` | `en.wikipedia.org` Bitcoin daily pageviews, 2026-09-01..2026-11-10 |
| `pageviews_ChatGPT.json` | `en.wikipedia.org` ChatGPT daily pageviews, 2026-09-01..2026-11-10 |
| `pageviews_Nvidia.json` | `en.wikipedia.org` Nvidia daily pageviews, 2026-09-01..2026-11-10 |
| `mediawiki_identity.json` | MediaWiki Action API identity/page-id query for curated articles |
| `manifest.json` | Replay mapping and recorded fetch timestamp |

The fixture fetcher hashes the raw fixture file bytes, so replay evidence raw
hashes match a live fetch of the same API response. Retrieval wall-clock
timestamps are excluded from evidence/calibration digests but remain in the
receipts.
