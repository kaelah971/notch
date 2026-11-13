# Phase 5C — Natural-Language Strategy Builder V1

The Strategy Builder is available at `/app/strategy-builder` and is a local-only
compiler for a small, explicit language over Wikimedia Pageviews. It does not
call NEAR AI, place entries, publish markets or claim a forecast probability.

## Supported language

The supported sentence shape is:

```text
If <supported topic> attention <rises|falls> by [at least] <percent>% over the [previous|prior|last] <days> days, predict <UP|DOWN> for the next <days> days.
```

Optional missing-data clauses are explicit:

```text
If data is missing, do not signal.
If missing data is unavailable, mark unavailable.
```

Supported topics and aliases:

- `Nvidia` — `NVIDIA`, `NVIDIA Corporation`, `NVDA`
- `Bitcoin` — `BTC`
- `ChatGPT` — `Chat GPT`
- `Artificial intelligence` — `AI`

Supported complete UTC-day windows and horizons are `1`, `3`, `7`, `14` and
`30` days. The source is fixed to Wikimedia Pageviews V1:
`en.wikipedia.org`, `all-access`, `user`, daily pageviews.

The parser returns `NEEDS_CONFIRMATION` when a critical field is absent. It does
not infer a missing topic, direction, threshold, horizon, outcome or missing-data
policy. It returns `UNSUPPORTED` for other sources, price, sentiment, odds,
wallet, trading, execution, unsupported topics, invalid horizons and ambiguous
directions.

## Versioned definition

The saved object uses `notch.strategy/1` and includes:

- generated `strategy_id` and editable `name`;
- fixed Wikimedia source methodology and supported topic;
- previous-to-current complete UTC-day observation window;
- signal direction and percentage threshold plus canonical basis points;
- forecast horizon and predicted outcome;
- explicit missing-data policy;
- `notch-historical-evaluation/1` methodology;
- an evaluator contract declaring complete windows and `no_lookahead: true`.

The behavior identity excludes the editable name, so equivalent supported
inputs compile to the same strategy ID and structured behavior. Saved definitions
are serialized under `notch.strategy.builder.v1` in browser local storage only.

## Example

Input:

```text
If NVIDIA attention rises by at least 10% over the previous 7 days, predict UP for the next 7 days. If data is missing, do not signal.
```

Compiled core:

```json
{
  "schema_version": "notch.strategy/1",
  "source": {
    "id": "wikimedia-pageviews-v1",
    "methodology_version": "wikimedia-pageviews-v1",
    "project": "en.wikipedia.org",
    "access": "all-access",
    "agent": "user",
    "metric": "daily_pageviews",
    "topic": "Nvidia"
  },
  "observation_window": {
    "unit": "full_utc_days",
    "comparison": "previous_window_to_current_window",
    "lookback_days": 7
  },
  "signal_direction": "RISING",
  "threshold_percent": 10,
  "threshold_bps": 1000,
  "forecast_horizon_days": 7,
  "predicted_outcome": "UP",
  "missing_data_policy": "NO_SIGNAL",
  "evaluation_methodology_version": "notch-historical-evaluation/1"
}
```

The editor also exposes the compiled evaluator handoff and runs a small dry-run
against the genuine frozen Nvidia Wikimedia fixture when the topic and source
match. That dry-run is a compilation/evaluation smoke test, not a live forecast
or performance claim.

## Boundary to NEAR AI

The structured definition and schema validator are the boundary for a future
model-generated draft. No model call is made by Phase 5C. Any future NEAR AI
proposal must pass the same `validateStrategy` and serialization checks as a
manual draft before it can be displayed or saved.
