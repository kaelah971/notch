# Notch Trend Radar (S3A)

Backend-only discovery service. It finds candidate attention topics from free
public sources, normalizes and deduplicates them, ranks them, evaluates whether
they can become measurable markets, and produces **PROPOSED** market drafts for
operator review.

It does **not** create markets, sign transactions, write settlement evidence or
touch the S2 contract.

## Quick start

```bash
# From the repository root; standard library only (Python 3.11+).
python -m services.trend_radar --data-dir var/trend_radar scan --summary

# Offline replay using recorded real API responses
python -m services.trend_radar --data-dir var/trend_radar_fixture \
  scan --fixtures services/trend_radar/fixtures --summary

# Inspect persisted results
python -m services.trend_radar --data-dir var/trend_radar candidates --summary
python -m services.trend_radar --data-dir var/trend_radar proposals --summary
python -m services.trend_radar --data-dir var/trend_radar review <proposal_id> \
  --approve --reason "reviewed for S3B"
```

The global `--data-dir` must appear before the subcommand. The scan writes
`last_scan.json` and a SQLite database under that directory (default
`var/trend_radar`, gitignored).

## Sources

| Source | Usage | Settlement eligible? |
| --- | --- | --- |
| Wikimedia Pageviews + MediaWiki API | Top daily articles, identity/redirects, 7-day coverage probes | **Yes**, as the only candidate settlement source |
| CoinGecko `/search/trending` | Trending coins + category context | No; discovery only |
| Hacker News (Algolia) | Front-page stories, points/comments | No; discovery only |

CoinGecko price or market-cap movement is never treated as attention. Hacker
News points/comments are discussion signals, not settlement measurements.

## Configuration

Environment variables (see `.env.example`):

- `RADAR_DATA_DIR` — data/cache/DB directory.
- `RADAR_USER_AGENT` — identified Wikimedia User-Agent.
- `COINGECKO_DEMO_API_KEY` — optional; never logged or committed.
- `RADAR_OPERATOR` — default reviewer label for CLI decisions.

No API key is required for the live smoke test. The public CoinGecko endpoint
may rate-limit; the radar isolates that failure and continues with Wikimedia and
Hacker News.

## Tests

```bash
python -m unittest discover -s services/trend_radar/tests -t . -v
```

Tests use recorded real API responses in `fixtures/`; they do not call live APIs.
See [`docs/S3A_TREND_RADAR_VERIFICATION.md`](../../docs/S3A_TREND_RADAR_VERIFICATION.md)
for the schema, ranking, eligibility, live scan evidence and S3B handoff.
