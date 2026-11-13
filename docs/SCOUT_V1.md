# Phase 5B — Notch Scout V1

Scout is a read-only attention-discovery view over completed Trend Radar
Wikimedia observations. It helps a user inspect unusual movements; it does not
create, publish, sign or settle a market.

## Supported scope

Scout V1 deliberately supports four topics already represented by the Radar's
stable Wikimedia mappings and fixtures:

- Nvidia
- Bitcoin
- ChatGPT
- Artificial intelligence

The API reads the stored Radar SQLite record. Wikimedia fetching, rate limits,
raw-response hashes and cache refresh remain owned by the existing Radar scan.
If the stored record is absent or unavailable, Scout returns an unavailable
state rather than inventing observations.

## Formula and thresholds

For the first and last complete daily observations in the stored window:

```text
change_bps = floor((current_views - baseline_views) * 10000 / baseline_views)
```

- `RISING`: `change_bps >= 2,000`
- `FALLING`: `change_bps <= -2,000`
- `STABLE`: otherwise
- `UNUSUAL`: `abs(change_bps) >= 4,000`
- minimum sample: 5 daily observations
- stale after: 48 hours from the stored Radar observation timestamp
- zero baseline: change is unavailable
- missing days: retained as missing; no imputation

Ranking is deterministic and capped at 100:

```text
movement = min(60, abs(change_bps) // 500)
rank = movement + sample_quality + freshness + baseline_quality
```

Sample quality is 20 for seven complete days, 10 for at least five days, and 0
otherwise. Freshness contributes 10 when not stale. Baseline quality contributes
10 when the baseline is at least 1,000 views. Ties are resolved by absolute
movement and then candidate ID.

## API

`GET /api/scout?direction=all|rising|falling&limit=12`

The response includes:

- topic and candidate ID;
- exact Wikimedia article and Pageviews API URLs;
- baseline/current dates and views;
- change bps, direction, status and uncertainty;
- missing-day list, freshness and minimum sample requirement;
- raw response hashes and a derived evidence digest;
- existing published-market match when the on-chain market and stored rule
  match the supported topic;
- a `REVIEW_ONLY` proposal draft only when the evidence is fresh, complete and
  notable.

Proposal drafts include the exact source, proposed full UTC-day dates,
threshold, formula and missing-data policy. They always contain
`human_review_required: true` and `published: false`.

## Reproducible stored example

The local live Radar record contains these genuine Wikimedia observations from
2026-11-04 through 2026-11-10:

| Topic | Baseline | Current | Change | Direction |
| --- | ---: | ---: | ---: | --- |
| Nvidia | 4,112 | 123,851 | 291,194 bps | Rising |
| Bitcoin | 7,955 | 4,359 | -4,521 bps | Falling |
| ChatGPT | 117,395 | 59,377 | -4,943 bps | Falling |

The records are attention measurements only. They do not establish sentiment,
causality, price direction, probability or a future market outcome.
