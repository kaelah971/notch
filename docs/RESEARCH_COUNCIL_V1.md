# Research Council V1

Phase 5E adds a read-only, evidence-grounded Research Council for a published market.
It is intentionally separate from wallets, entry intents, market publication, oracle
settlement, and contract code.

## Workflow

1. The API loads the published rule and verifies that its rule hash matches the
   on-chain market hash.
2. It loads the verified oracle receipt when available, bounded Wikimedia attention
   observations, and same-topic/same-methodology historical context.
3. Those records are assembled once into a `notch.research-council.snapshot/1`.
   Every role receives the same snapshot and input digest.
4. Three roles are produced:
   - **Bull Analyst** — cited observations that may support UP, plus counterpoints.
   - **Bear Analyst** — cited observations that may support DOWN, plus counterpoints.
   - **Evidence Verifier** — citation coverage, scope, and unresolved gaps.
5. Citation, number/date, banned-claim, role-position, and source-reference
   validation runs before an AI role is accepted.
6. Disagreement tracking compares the cited evidence sets without producing a
   probability or choosing a winner.
7. A safe audit record records the snapshot, source IDs, role statuses, citation
   statuses, and execution boundary. Prompts, raw provider responses, API keys,
   and private reasoning are never persisted.

## Generation modes

- `DETERMINISTIC_EVIDENCE_LENSES`: no AI key or AI was disabled. The roles are
  clearly labeled source-only deterministic lenses.
- `AI_GENERATED`: one bounded NEAR AI JSON completion produced all three roles and
  every role passed validation. Inference remains unverified unless the exact
  cryptographic attestation protocol is available.
- `AI_UNAVAILABLE_FALLBACK`: model discovery, input limits, or provider failure
  prevented generation.
- `INVALID_AI_FALLBACK`: a role response failed validation and that role fell back
  to the deterministic lens.
- `MIXED_AI_AND_FALLBACK`: some roles were accepted while others fell back.

The service makes at most one AI completion per council generation and respects the
existing `NearAIConfig.max_calls_per_run` setting. No live inference was required
for local verification.

## API

- `POST /api/markets/{market_id}/council`
  - `{ "allow_ai": true|false, "force": true|false }`
  - `allow_ai` defaults to true, but a missing `NEAR_AI_KEY` always returns the
    deterministic evidence lenses.
- `GET /api/markets/{market_id}/council`
  - returns the latest persisted council record, if one exists.

The response includes `snapshot.snapshot_digest`, `snapshot.source_ids`, role
citation reports, `disagreement`, `audit`, `result_digest`, and explicit
`execution` flags showing that no wallet action, signature, broadcast, publication,
or settlement occurred.

## Storage and reproducibility

Council records are stored in the SQLite path configured by
`RESEARCH_COUNCIL_DB_PATH` (default `var/web_api/research_council.sqlite3`). The
snapshot digest is a deterministic SHA-256 label over the canonical bounded input
package. It is an integrity/reproducibility identifier, not a provider attestation.

## Limits

- Wikimedia pageviews measure attention, not sentiment, causality, price direction,
  or a calibrated probability.
- Missing observations and unsupported topics remain explicit; no values are
  imputed.
- Disagreement is descriptive. It does not authorize staking, publication, or
  autonomous execution.
- Genuine AI output is not cryptographically attested in this phase.
