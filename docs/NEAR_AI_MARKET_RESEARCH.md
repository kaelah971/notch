# Phase 5A — NEAR AI Market Analyst V1

Notch market research is an explicit, read-only action at
`POST /api/markets/{market_id}/research`. It is separate from ordinary market
reads, wallet flows, entry intent, Practice, Pulse, rankings, and settlement.

## Grounding contract

The server builds one bounded packet from:

- the onchain-matched, published market rule and exact resolution formula;
- complete-day Wikimedia Pageviews observations, with source URLs, timestamps,
  observation hashes, raw-response hashes, and stable source IDs;
- verified current oracle evidence when a finalized receipt exists; and
- historical replay/calibration context only when topic, source, observation
  span, formula, threshold, and baseline methodology match.

The observation window is capped at 31 days and the grounded prompt is capped
at 20,000 characters. Missing rows remain unavailable; there is no imputation,
target-window lookahead, fabricated outcome, or probability estimate.

## Structured output

A brief contains separate `supporting_up`, `supporting_down`,
`key_assumptions`, and `historical_context` claim lists. Every `FACT` or
`INTERPRETATION` claim must cite a supplied source ID. `UNKNOWN` is required
when a side is unsupported. Numeric/date validation, banned-claim validation,
unknown-field checks, and citation validation run before any AI brief is
returned. Invalid or unavailable AI output falls back to deterministic source-
only text.

## Provider and verification

The provider is the official NEAR AI Cloud OpenAI-compatible API at
`https://cloud-api.near.ai/v1`, configured by server-side `NEAR_AI_KEY` and
`NEAR_AI_MODEL`. The key is never sent to the browser or included in a brief.
The current integration records safe request/model/input metadata, but does not
claim cryptographic attestation. The UI shows **Verified Inference** only when
the response metadata is explicitly `verified`; the current expected status is
`unavailable` until exact request/response bytes, gateway/model attestation
preflight, and response-signature verification are implemented.

## Test and runtime status

The deterministic and mock-provider coverage is in:

- `services/near_ai/tests/test_research.py`
- `services/web_api/tests/test_repositories.py`
- `services/web_api/tests/test_api.py`

A live provider call was not performed in the current environment because
`NEAR_AI_KEY` is not configured. No deployment, contract change, signing,
broadcast, or blockchain transaction is part of this slice.
