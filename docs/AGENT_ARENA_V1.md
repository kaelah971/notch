# Phase 6A — Agent Arena V1

Status: implemented as a local, walletless, deterministic historical replay.

## Boundary

Agent Arena V1 is a choose → review → run → inspect → adjust workflow. It does not deploy, sign, call a wallet, publish a market, enter a position, settle a contract, call NEAR AI, or create fabricated agent identities. Virtual credits have no USDC value.

The route is `/app/arena`. The desktop sidebar exposes **Agent Arena**; the existing Strategy Builder remains the place to create and revise a saved user rule.

## Match methodology

- **Methodology:** `notch-agent-arena/1`
- **Participant contract:** `notch-agent-arena-participant/1`
- **Dataset:** `wikimedia-nvidia-2026-10-01-2026-11-10`, version `1`
- **Source:** genuine Wikimedia Pageviews observations for Nvidia; no imputation or lookahead
- **Signal cutoff:** the end of the signal date at `23:59:59Z`
- **Signal windows:** previous 7 complete UTC days compared with current 7 complete UTC days
- **Target:** following 7 complete UTC days
- **Candidates:** 21, all 21 eligible in the frozen fixture
- **Overlapping windows:** each 21-observation candidate advances by one day and overlaps the prior candidate by 20 observations; counts are not independent trials

The built-in Attention Momentum trigger is the preserved Phase 5D example: falling attention by at least 5% predicts DOWN. Contrarian / Reversal uses the same falling trigger and predicts UP. Always-UP and Always-DOWN are matched benchmarks on the same eight benchmark signal dates, rather than additional evidence or strategy claims.

## Risk and scoring

Every selected participant starts at **1,000 virtual credits**.

- Requested stake: 10% of current balance.
- Maximum position: 25% of starting balance (`250` credits).
- No negative balance; if the minimum stake cannot be met, the decision is explicitly skipped as `INSUFFICIENT_BALANCE`.
- Correct: stake is returned plus an equal virtual reward (`+stake`).
- Incorrect: stake is lost (`-stake`).
- Void: supported as a refunded state, although the frozen fixture has no void outcomes.
- Pending: represented in the result schema and remains zero because historical target windows settle immediately.
- Ranking: ending credits, then accuracy, then correct calls, then stable participant ID.
- Maximum drawdown is calculated from the settled equity curve and is null when there is no settled sample.

Each participant result includes correct/incorrect/pending/voided counts, skipped and unavailable windows, sample size, accuracy, ending credits, drawdown, risk caps prevented, strategy hash, and the complete decision ledger. Each ledger row separates `signal_evidence_refs` available at the cutoff from `outcome_evidence_refs` used only for post-cutoff historical resolution; the combined refs are never used to generate the signal.

## Participants and versioning

The arena ships four deterministic participants:

1. `bot_attention_momentum_v1` — Attention Momentum.
2. `bot_contrarian_reversal_v1` — Contrarian / Reversal.
3. `baseline_always_up_v1` — matched Always-UP benchmark.
4. `baseline_always_down_v1` — matched Always-DOWN benchmark.

A saved local strategy is offered as one additional `USER_STRATEGY` slot only when it uses the supported Nvidia Wikimedia source, 7-day observation window, and 7-day horizon. Incompatible saved strategies are shown with an explicit exclusion reason. The saved strategy keeps its `notch.strategy/1` identity and canonical strategy hash; each arena participant also carries a participant configuration hash.

## Reproducible fixture result

Running the four built-ins against the frozen fixture produced:

| Rank | Participant | Ending credits | Correct / incorrect | Accuracy | n | Skipped | Unavailable | Max drawdown |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Always-DOWN baseline | 1,175 | 5 / 3 | 62.5% | 8 | 13 | 0 | 435 |
| 2 | Attention Momentum | 1,175 | 5 / 3 | 62.5% | 8 | 13 | 0 | 435 |
| 3 | Always-UP baseline | 787 | 3 / 5 | 37.5% | 8 | 13 | 0 | 408 |
| 4 | Contrarian / Reversal | 787 | 3 / 5 | 37.5% | 8 | 13 | 0 | 408 |

Tie order is intentional and stable; the arena does not invent a winner when ending credits, accuracy, and correct-call counts are equal.

- Match ID: `arena_match_935505c1`
- Result digest: `fnv1a32:dfb6611a`
- Dataset content SHA-256: `4661cc83a880931a392d3745fe234869bae3f191b4bff4229cb6ad2682175cfd`
- Source fixture SHA-256: `f372687814e75ca213ef31e014a2a9a8dc204340f249a44922ae9e1401e436f2`
- Attention Momentum strategy hash: `fnv1a32:7d6d7c32`
- Contrarian / Reversal strategy hash: `fnv1a32:87d80c17`
- Always-UP participant config hash: `fnv1a32:1f0ccd64`
- Always-DOWN participant config hash: `fnv1a32:f78ccc8e`

These are local deterministic identity labels, not cryptographic attestations. The dataset SHA-256 is the integrity value.

## Implementation files

- `web/src/arena/arena.ts` — participant definitions, compatibility, common windows, deterministic replay, risk/accounting, ranking, ledgers, provenance, and execution boundary.
- `web/src/pages/Arena.tsx` — choose/review/run/results/inspect UI and saved-strategy slot.
- `web/src/pages/Arena.css` — responsive desktop/mobile arena surface.
- `web/src/practice/fixtures/nvidia-momentum-v1.ts` — reused genuine frozen Wikimedia fixture.
- `web/src/main.tsx` — `/app/arena` route.
- `web/src/components/nav.ts` — Agent Arena navigation item.
- `web/tests/arena.test.mjs` — deterministic, fairness, no-lookahead, risk, missing-data, compatibility, ranking, and no-execution tests.
- `web/package.json` — `npm run test:arena`.

The engine reuses `notch.strategy/1` definitions and `evaluateStrategy` rather than maintaining a second signal evaluator. Baselines share the reference participant’s eligible windows and benchmark signal dates. Decision evidence references are deterministic Wikimedia IDs such as `wikimedia:en.wikipedia.org:Nvidia:<date>`.

## Verification

- `npm run test:arena` — 7 passed.
- Existing strategy, evaluation, practice, and backtest suites — passed during the Phase 6A verification run.
- `npm run build` — passed; only existing bundle-size and dependency `eval` warnings remain.
- Browser smoke checked the arena at 1440px; the page reported no horizontal overflow (`scrollWidth === viewport width`).
- Responsive CSS includes 850px and 560px breakpoints for the participant grid, rules, leaderboard, ledger, and provenance cards.

Suggested screenshots from the local verification run:

- `var/notch-arena-1440.png` — choose/review/run surface.
- `var/notch-arena-1440-results.png` — rendered results and inspectable ledger.

## Limitations and Phase 6B readiness

- This is one genuine topic, one bounded fixture, and a small overlapping sample. It is not a general performance claim.
- There is no remote match persistence, public API, multi-user identity, or anti-cheat protocol.
- Saved strategies are browser-local and must match the V1 compatibility contract; unsupported topics and horizons remain excluded.
- No live observations are fetched during a replay, and no settlement or publication path is connected.
- Cryptographic attestations, adversarial agents, online learning, continuous monitoring, and autonomous execution are out of scope.

Phase 6B is now available only as the controlled, browser-local paper workflow documented in [`docs/AUTOPILOT_V1.md`](AUTOPILOT_V1.md) and the browser proof at [`docs/evidence/phase6_agent_arena_autopilot_browser_20261114.json`](evidence/phase6_agent_arena_autopilot_browser_20261114.json). It does not attach a wallet, settle a replay, publish a market, or execute on-chain. Any live execution or settlement work remains blocked until server-owned snapshots, immutable participant manifests, authorization, replay verification, multi-user identity, abuse controls, signer isolation, and finality constraints are independently verified.
