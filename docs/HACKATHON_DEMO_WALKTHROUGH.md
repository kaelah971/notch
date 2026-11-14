# Notch — judge-ready hackathon demo walkthrough

**Read-only readiness snapshot:** NEAR Testnet final block `277669193`,
`2026-11-14T14:27:48Z`. Testnet assets only. No transaction, claim, refund,
quote, or deployment is part of this walkthrough.

## Demo promise

Notch is for a researcher or forecaster who wants to move from source-backed
attention research to a real, auditable prediction. The demo shows a genuine
Base Sepolia → NEAR Testnet funding proof and a genuine NEAR prediction. It does
not pretend that the future market has already resolved.

The funded account is:

```text
4c9c0572fedb185055adb0acce14c2cf0f8652f07f3500fba7bacd3dadfad2c0
```

## 1. Research and evidence analysis

**Best UI route:** `/app/markets` →
`/app/markets/s3b-future-btc-20261116-20261123`

Use the market detail page to show:

- the exact Bitcoin Wikimedia Pageviews question;
- the locked rule, threshold and UTC observation dates;
- the source and resolution timeline;
- the stake pool read from `market.notch-dev.testnet`;
- the explicit boundary that future evidence is not available yet.

`Request research brief` is read-only. Show only the returned source-backed or
`NON_AI_FALLBACK` result; do not claim that an AI inference succeeded. The
historical Nvidia replay has a preserved source-only research record in
`docs/evidence/s5_market_nvidia_replay_20261112.json`.

## 1A. Private research, strategy and paper workflow

These routes are local/browser or wallet-session surfaces; they do not create a
market or place a token-backed entry:

- `/app/discover` — deterministic Scout candidates and source references.
- `/app/vault` — owner-restricted application storage. It is **not** end-to-end
encryption, anonymity, or on-chain storage. A new save requires the existing
NEP-413 wallet ownership session; do not sign during a read-only demo unless the
judge has explicitly approved it.
- `/app/strategy-lab` — replay a saved rule against the frozen Nvidia fixture.
- `/app/arena` — run the four deterministic participants and inspect
`arena_match_935505c1` / `fnv1a32:dfb6611a`.
- `/app/autopilot?agent=bot_attention_momentum_v1` — activate browser-local
paper policy and inspect risk/audit rows. The current published market set is
expected to produce `BLOCKED`; the separate historical `PAPER_EXECUTED` proof
is preserved in
[`docs/evidence/phase6_agent_arena_autopilot_browser_20261114.json`](evidence/phase6_agent_arena_autopilot_browser_20261114.json).

The future market detail also exposes **AI MARKET RESEARCH** and **RESEARCH
COUNCIL** controls. For this read-only proof, show their truthful `UNAVAILABLE`
state when no cached record exists; do not trigger a new NEAR AI request and do
not describe deterministic fallback as live inference.

## 2. Cross-chain Testnet funding

**Best UI route:** `/app/portfolio` (show the balance; do not start a new
funding flow).

The complete proof is preserved in:

- [`docs/PHASE_7D_CROSS_CHAIN_FUNDING.md`](PHASE_7D_CROSS_CHAIN_FUNDING.md)
- [`docs/evidence/phase7d_base_sepolia_near_success_20261114.json`](evidence/phase7d_base_sepolia_near_success_20261114.json)

The proof covers the Base Sepolia ERC-20 transfer, Tidepool settlement,
`0.450000` excess refund, intent hashes, and the finalized NEAR balance delta.
Do not request another quote or deposit.

## 3. Existing real prediction entry

**Best UI route:** `/app/portfolio` → position row → market detail.

The entry already exists and must not be repeated:

- Transaction: [`1JEFnWsuh2jWpYPZV957WgNFdwbv7kTTQ7GUs7t72oh`](https://testnet.nearblocks.io/txns/1JEFnWsuh2jWpYPZV957WgNFdwbv7kTTQ7GUs7t72oh)
- Method: `usdc.tidepool-sandbox.testnet.ft_transfer_call`
- Amount: `1,000,000` base units
- Market: `s3b-future-btc-20261116-20261123`
- Outcome: `0` / `UP`
- Receipt: `SuccessValue`
- Contract event: `position_entered`

The current finalized contract read is stakes `[1000000, 0]`, claimable `0`,
and claim state `open`. The entry predates the Phase 7D funding transfer; this
walkthrough makes no unsupported claim that the later bridge funding paid for
that earlier entry.

## 4. Forecast Passport — pending, not resolved

**Best UI route:**
`/app/p/4c9c0572fedb185055adb0acce14c2cf0f8652f07f3500fba7bacd3dadfad2c0`

The live position classifies as:

```text
Called: UP
Prediction status: PENDING
Accuracy: unavailable (no completed prediction)
```

This follows the existing wallet positions API and deterministic
`classify_prediction` path. A finalized market would become `CORRECT`,
`INCORRECT`, or `VOIDED`; no such result is asserted today.

## 5. Historical replay settlement example

**Best UI routes:**

- `/app/markets/s3b-short-trend-nvidia-20261112T040029Z`
- `/app/markets/s3b-short-battle-btc-chatgpt-20261112T040029Z`

Both are clearly labeled **Historical replay**, not forward predictions.
Current onchain reads show:

| Market | Final outcome | Evidence hash | Current funded-wallet position |
|---|---|---|---|
| Nvidia replay | `UP` | `sha256:583eac071d0b3d8a9ad661f02180c2d1c58fbac435e68b5c6346a28348257e06` | none |
| Bitcoin/ChatGPT replay | `Bitcoin` / `TOPIC_A` | `sha256:ad15ea91fa97e32cc97e5dd94dc5db72a511e5fa980b1e8c7615b2db0ccd3e5d` | none |

The complete historical lifecycle is documented in
[`docs/evidence/s2_5_execution_20261112.json`](evidence/s2_5_execution_20261112.json)
and [`docs/S2_5_ONCHAIN_VERIFICATION.md`](S2_5_ONCHAIN_VERIFICATION.md).

## 6. Claim/refund functionality

**Best UI route:** `/app/portfolio`.

The existing UI shows `Claim payout` only when the connected account has
`claim_state = claimable`. The transaction it prepares is:

```json
{
  "receiver_id": "market.notch-dev.testnet",
  "method": "claim",
  "args": {"market_id": "<resolved-or-voided-market>"},
  "attached_deposit": "0",
  "gas": "100 Tgas"
}
```

The contract also exposes `claim_refund`; the generic `claim` path covers a
voided market's refundable stake. No claim/refund is currently available for
the funded wallet because it has no position in either resolved replay.

Historical claim functionality **was** live-verified for the separate
`notch-dev.testnet` replay positions:

- Nvidia claim: [`C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr`](https://testnet.nearblocks.io/txns/C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr)
- Bitcoin/ChatGPT claim: [`C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU`](https://testnet.nearblocks.io/txns/C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU)

Each returned `1.000000` test-USDC stake. This proves settlement and
collateral recovery, not profit and not a current-wallet claim.

## Truthful demo boundary

### Verified today

- Phase 6 Arena → Paper Autopilot browser proof and deterministic fixture audit.
- Private Research Vault owner boundary and no-public-feed isolation.
- Phase 7D Base Sepolia → NEAR Testnet funding proof.
- Existing real future-market entry and onchain `UP` position.
- Forecast Passport pending classification path.
- Two resolved historical replay outcomes.
- Historical replay claim transactions and payout accounting.

### Not verified today

- The future Bitcoin market has not resolved.
- No current-wallet claim or refund has occurred.
- No current future-market outcome is known.
- No successful AI inference should be claimed as part of the proof; the live provider remained unavailable/time-out prone.
- No public browser/API deployment exists in the repository. Local browser verification used the API with `NEAR_RPC_URL=https://archival-rpc.testnet.fastnear.com` because the default public RPC was rate-limited.
- The Vault is owner-restricted application privacy, not cryptographic encryption.

## Recommended three-minute judge order

1. **0:00 — Discover and rule.** Open `/app/discover`, show a deterministic
Scout candidate, then open `/app/markets/s3b-future-btc-20261116-20261123`.
Show the locked Bitcoin Wikimedia rule, actual attention chart, open deadline,
and the honest missing-evidence / unavailable research boundary.
2. **0:35 — Private research boundary.** Open `/app/vault` and show `PRIVATE ·
owner-only`, the NEP-413 requirement, and the explicit “not end-to-end
encryption” disclosure. Do not sign or save during a read-only run.
3. **0:50 — Strategy to paper.** Open `/app/strategy-lab`, then `/app/arena`.
Run the deterministic four-participant match and inspect Attention Momentum.
Follow **Send to paper Autopilot**, activate `PAPER_AUTO`, run `Evaluate Now`,
and show the current live set recorded as `BLOCKED` with audit details. Use the
Phase 6 evidence file for the separate historical `PAPER_EXECUTED` example.
4. **1:55 — Real read-only state.** Open `/app/portfolio` and the funded
account’s Passport route. Show the existing balance/position only; do not
enter, claim, refund, quote, or transfer. The future call remains `PENDING` and
accuracy remains unavailable.
5. **2:35 — Funding proof and close.** Use the Phase 7D document/evidence JSON
to show the already-verified Base Sepolia → NEAR Testnet Tidepool proof. State
clearly that it is Testnet sandbox evidence, not official NEAR Intents Mainnet,
and end with the future market’s resolution eligibility at
`2026-11-25T12:00:00Z`.
