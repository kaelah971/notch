# Phase 6B — Autopilot V1

Status: implemented as controlled, browser-local paper execution. No on-chain execution is connected.

## User journey

`Saved strategy → historical review → risk configuration → activate → Evaluate Now → inspect decisions → pause/stop`

The route is `/app/autopilot`. It accepts one validated saved `notch.strategy/1` revision at a time. The selected revision is evaluated against the genuine frozen Nvidia Wikimedia fixture before activation. Unsupported topics such as Bitcoin remain blocked because the current supported fixture does not match them.

Evaluate Now is a user-triggered action. There is no browser timer, server scheduler, background worker, 24/7 claim, wallet call, signer, broadcast, market publication, contract interaction or paid NEAR AI request. Closing the browser stops forward evaluation.

## Policy contract

`web/src/autopilot/autopilot.ts` defines `notch.autopilot/1` and `notch.autopilot-policy/1`.

A policy stores:

- policy ID and incrementing policy version;
- strategy ID and canonical strategy revision hash;
- `ACTIVE`, `PAUSED` or `STOPPED` status;
- `MANUAL_REVIEW` or `PAPER_AUTO` mode;
- virtual budget;
- fixed-credit or percentage stake;
- maximum exposure;
- maximum simultaneous positions;
- daily virtual-loss limit;
- decision cooldown.

Default configuration is 1,000 virtual credits, 10% allocation, 250-credit maximum exposure, one open position, 100-credit daily-loss limit and a 900-second cooldown. The domain validator rejects invalid budgets, stakes, exposure, position counts, loss limits and cooldowns; UI validation is not the enforcement boundary.

### Action statuses

- `PAPER_ENTRY_APPROVED`
- `NEEDS_MANUAL_REVIEW`
- `BLOCKED_BY_RISK`
- `MARKET_INELIGIBLE`
- `INSUFFICIENT_EVIDENCE`
- `COOLDOWN`
- `ALREADY_PROCESSED`
- `PAUSED`

Manual-review mode creates a review row without a virtual position. Approval rechecks the local risk ledger before creating a paper-only position. Paper-auto mode creates the virtual position after the same checks.

## Evaluation pipeline

```text
Observe
  → evaluate saved strategy
  → verify source, topic, methodology, choices, formula and rule hash
  → verify market status and authoritative close deadline
  → reject replay/closed/paused/stale/missing evidence
  → apply budget, exposure, position, loss and cooldown rules
  → decide
  → persist a local audit row
```

Market compatibility requires all of the following:

- published `trend_trading` mode;
- exactly `UP` and `DOWN` choices in contract order;
- matching Wikimedia source ID and source metadata;
- matching topic from the published rule;
- verifiable strategy window and horizon;
- supported integer growth-threshold resolution formula;
- non-replay market;
- open status, future display status, entries enabled and deadline in the future;
- matching market/rule hash.

If a rule cannot expose the required field, the action is blocked as unverifiable rather than guessed. A historical Nvidia strategy is never applied to a Bitcoin market.

Forward evaluation rejects the frozen fixture when its observation end is before the current day. Historical simulation is a separately labelled domain mode for deterministic tests and does not claim forward freshness.

## Audit and idempotency

Each action records:

- policy ID and policy version;
- strategy revision/hash;
- evidence snapshot ID, digest and cutoff;
- market ID and rule hash;
- decision cutoff;
- complete risk configuration snapshot;
- requested stake, applied stake and exposure before/after;
- action status, reason code and explanation;
- simulated position ID when approved;
- run timestamp and run mode;
- prediction, signal momentum and source data cutoff.

The idempotency key is based on policy ID/version, strategy revision hash, market ID and decision cutoff. Repeating the same evaluation produces `ALREADY_PROCESSED` and does not create a second virtual position.

Configuration and audit state are stored under `notch.autopilot.v1` in browser local storage. The state is editable and not server-verified. Malformed rows are discarded on read. No prompts, keys, raw provider bodies or private reasoning are persisted.

## Reproducible blocked-action demonstration

Browser verification used the saved strategy:

- strategy: `strategy_d7382362`;
- rule: Nvidia falling attention by 5% over 7 days → DOWN over 7 days;
- strategy revision hash: `fnv1a32:0ed0a683`;
- mode: Manual review;
- budget: 1,000 credits;
- allocation: 10% / 100 requested credits;
- maximum exposure: 250 credits;
- maximum positions: 1;
- daily loss limit: 100 credits;
- cooldown: 900 seconds.

The current published-market API returned three market definitions. The run recorded only `MARKET_INELIGIBLE` decisions and created zero paper positions. Observed blockers included:

- historical replay markets are not forward paper targets;
- authoritative entry deadlines had passed for closed markets;
- Bitcoin/Battle topics did not match Nvidia;
- battle resolution semantics did not match UP/DOWN trend semantics;
- published rules did not expose the saved strategy's lookback/horizon;
- no eligible market was fabricated.

The policy remained at 1,000 available credits and zero exposure. A repeated evaluation is covered by tests and produces `ALREADY_PROCESSED` for the same idempotency key. A paused or stopped policy produces `PAUSED` and refuses new actions.

The genuine evidence fixture is:

- dataset: `wikimedia-nvidia-2026-10-01-2026-11-10`, version `1`;
- dataset SHA-256: `4661cc83a880931a392d3745fe234869bae3f191b4bff4229cb6ad2682175cfd`;
- source fixture SHA-256: `f372687814e75ca213ef31e014a2a9a8dc204340f249a44922ae9e1401e436f2`.

## Files

- `web/src/autopilot/autopilot.ts` — policy schema, validation, persistence, market compatibility, risk engine, idempotency and audit actions.
- `web/src/pages/Autopilot.tsx` — strategy selection, historical review, policy form, controls, Evaluate Now and audit history.
- `web/src/pages/Autopilot.css` — responsive desktop/mobile UI.
- `web/src/main.tsx` — `/app/autopilot` route.
- `web/src/components/nav.ts` — Paper Autopilot navigation item.
- `web/tests/autopilot.test.mjs` — policy, market, risk, cooldown, stale evidence, no-lookahead, persistence and no-execution coverage.
- `web/package.json` — `npm run test:autopilot`.

## Verification

- `npm run test:autopilot`: 10 passed.
- Phase 6A `npm run test:arena`: passed.
- Existing strategy, evaluation, practice, backtest, forecast and research suites: passed.
- `npm run build`: passed.
- `npm run lint`: passed with existing repository warnings.
- `git diff --check`: passed.
- Browser smoke: 1440px, 390px and 320px; all reported `scrollWidth === viewport width`.

Screenshots:

- `var/notch-autopilot-1440.png`
- `var/notch-autopilot-390.png`
- `var/notch-autopilot-320.png`

## V1 limitations

- There is no remote policy persistence, multi-device sync, server authorization, anti-cheat boundary or server-owned audit ledger.
- Forward evidence uses the existing frozen fixture and therefore blocks when it is stale; no live Wikimedia fetch was added for this milestone.
- Current market compatibility is conservative: missing rule metadata blocks instead of inferring compatibility.
- Paper positions are not resolved automatically and have no monetary or contractual value.
- The browser can be closed, storage can be edited and the local ledger is not an attestation.

## Requirements for Autopilot V2 on-chain execution

Before any real-money or on-chain path, Notch needs server-owned immutable policy snapshots, authenticated user identity, explicit authorization and revocation, least-privilege session permissions, spending and exposure limits enforced outside the browser, transaction simulation, replay protection, nonce/finality handling, signer isolation, emergency stop, rate limits, independent audit trails, production CORS/auth configuration, attestation/verification of model and evidence inputs, and a mandatory human approval boundary. V1 does not authorize future trades and must not be wired directly to the existing entry-intent or wallet paths.
