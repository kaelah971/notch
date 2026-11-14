# Notch — five-minute judge path

**Live app:** [trynotch.vercel.app](https://trynotch.vercel.app)<br>
**Proof ledger:** [`PROOF.md`](PROOF.md)<br>
**Architecture:** [`ARCHITECTURE.md`](ARCHITECTURE.md)

This is a read-only showcase path. Do not request a quote, deposit collateral,
create a market, enter a position, resolve a market or claim a payout during the
 demo. Testnet assets have no value, and the existing proof is already recorded.

## Before the timer

Have these tabs ready:

- [Live Notch](https://trynotch.vercel.app)
- [Future Bitcoin market](https://trynotch.vercel.app/app/markets/s3b-future-btc-20261116-20261123)
- [Historical Nvidia replay](https://trynotch.vercel.app/app/markets/s3b-short-trend-nvidia-20261112T040029Z)
- [Verified demo Passport](https://trynotch.vercel.app/app/p/4c9c0572fedb185055adb0acce14c2cf0f8652f07f3500fba7bacd3dadfad2c0)
- [Agent Arena](https://trynotch.vercel.app/app/arena)
- [Paper Autopilot](https://trynotch.vercel.app/app/autopilot?agent=bot_attention_momentum_v1)

The Passport URL is a public chain read for the documented demo account. It is
not a private session and does not expose a key.

## 0:00 — Establish the product

Open the [landing page](https://trynotch.vercel.app).

**Show:**

- “The internet moves. Make your call.”
- **Explore Markets** and the **Connect Wallet** boundary.
- The product premise: discover attention, make an explicit call, verify the
  outcome.

**Expected result:** the app loads without a wallet. No action is signed.

## 0:30 — Discover the market set

Open [Markets](https://trynotch.vercel.app/app/markets).

**Show:**

- The open Bitcoin forecast: “Will Bitcoin’s attention jump 23% in one week?”
- The two **Resolved demonstration** cards.
- The distinction between `open_future` and
  `historical_replay_resolved`.
- The Testnet / no-value footer.

**Say:** Notch does not hide the difference between a forward forecast and a
known-outcome replay. The future market has a real rule and deadline, but no
outcome yet.

## 1:05 — Open genuine historical evidence

Open the [Nvidia historical replay](https://trynotch.vercel.app/app/markets/s3b-short-trend-nvidia-20261112T040029Z).

**Show:**

- The Wikimedia Pageviews question and UTC dates.
- The `RESOLVED DEMONSTRATION` label.
- The attention chart and the `UP` outcome.
- The note explaining that this is not a forward prediction.
- The source/rule/evidence area lower on the page if scrolling is available.

**Expected result:** a real observed chart and a resolved on-chain market state.
The replay is evidence of settlement mechanics, not a claim of future accuracy.

## 1:45 — Show the live forecast boundary

Open the [future Bitcoin market](https://trynotch.vercel.app/app/markets/s3b-future-btc-20261116-20261123).

**Show:**

- The locked source: Wikimedia daily pageviews for Bitcoin.
- The 23% threshold, baseline/target dates and entry deadline.
- `OPEN` / pending state and the absence of a winning outcome.
- Research controls only as truthful `UNAVAILABLE` / no-cache states when shown.

**Expected result:** no invented research, resolution or payout. The future
market remains unresolved until its legitimate eligibility time.

## 2:25 — Inspect Forecast Passport / Portfolio

Open the [documented demo Passport](https://trynotch.vercel.app/app/p/4c9c0572fedb185055adb0acce14c2cf0f8652f07f3500fba7bacd3dadfad2c0).

**Show:**

- The `UP` call on the future Bitcoin market.
- `PENDING` prediction status.
- Accuracy unavailable because the market has not resolved.
- The public NEAR Testnet account link if the page exposes it.

Then optionally open [Portfolio](https://trynotch.vercel.app/app/portfolio).
Without a connected wallet it correctly asks for a wallet instead of showing
simulated holdings.

**Wallet alternate:** If a judge has a NEAR Testnet wallet already configured,
connect it only to inspect finalized balances and positions. Do not approve a
new wallet action for this walkthrough.

## 3:05 — Show private research boundaries

Open [Private Research Vault](https://trynotch.vercel.app/app/vault).

**Show:**

- `PRIVATE · OWNER-ONLY`.
- The NEP-413 wallet ownership requirement.
- The explicit statement that Vault storage is not end-to-end encryption.
- The fact that private theses are not sent to AI automatically.

**Expected result:** the page is useful without a wallet, but private records
remain locked. Do not sign or create a record during the judge path.

## 3:35 — Compare strategies in Agent Arena

Open [Agent Arena](https://trynotch.vercel.app/app/arena).

**Show:**

- Attention Momentum, Contrarian / Reversal and the two baselines.
- The same dataset / same cutoffs language.
- `WALLETLESS · HISTORICAL ONLY`.
- The controlled-competition disclosure: deterministic participants, no live
  agents, wallet calls or transactions.

The browser proof records match `arena_match_935505c1` and strategy hash
`fnv1a32:7d6d7c32` in
[`evidence/phase6_agent_arena_autopilot_browser_20261114.json`](evidence/phase6_agent_arena_autopilot_browser_20261114.json).

## 4:05 — Follow the paper-only handoff

Open [Paper Autopilot](https://trynotch.vercel.app/app/autopilot?agent=bot_attention_momentum_v1).

**Show:**

- The `PAPER ONLY · LOCAL DEVICE` label.
- Historical review metrics and the warning that historical accuracy does not
  authorize a forward action.
- Explicit risk policy fields.
- The no-autonomous-on-chain-execution disclosure.

**Expected current result:** the published three-market set is ineligible for
paper action and produces `BLOCKED` rows with audit IDs. The historical fixture
separately proves a deterministic `PAPER_EXECUTED` record; it is not a live
trade and is documented in the evidence file above.

## 4:35 — Verify real NEAR Testnet proof

Open [`PROOF.md`](PROOF.md) and choose one of these already-completed links:

1. [Historical Nvidia claim](https://testnet.nearblocks.io/txns/C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr)
2. [Historical Bitcoin/ChatGPT claim](https://testnet.nearblocks.io/txns/C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU)
3. [Market contract deployment](https://testnet.nearblocks.io/txns/EFJvJVmBMWAh4Rqaxh7s2uCn72Hm1uXV3yc9zmEaEeDj)

**What to verify:** NEAR Testnet network, receiver
`market.notch-dev.testnet`, method `claim` for the historical links, successful
receipt and the associated market ID in the proof notes.

**What it establishes:** the deployed contract and historical settlement / claim
path. It does not establish profit, Mainnet operation or a current-wallet claim.

## 4:50 — Review the cross-chain funding proof

Open [`PHASE_7D_CROSS_CHAIN_FUNDING.md`](PHASE_7D_CROSS_CHAIN_FUNDING.md).

Use the linked [Base Sepolia source transfer](https://sepolia.basescan.org/tx/0x39623909068e564ad2304091dbe1477688e5e51f4e908674ff219f84217c2d7b),
[Base Sepolia refund](https://sepolia.basescan.org/tx/0x21acf175808d9c05b2b67dcee4b1dd18ebef0f73892037cd0411699b8145f49c) and
[NEAR settlement](https://testnet.nearblocks.io/txns/8b5WKmEqBpVu8mLDAbKHmrDHEiJCZEwBkHYqbryPKfum).

**Expected proof:**

- Base Sepolia ERC-20 receipt succeeded.
- `1.500000` test-USDC was deposited to the Tidepool address.
- `0.450000` excess test-USDC was refunded.
- Finalized NEAR balance moved from `99.000000` to `100.047270` test-USDC,
  a `1.047270` destination delta.

This proves a Testnet sandbox funding path and destination observation only. It
does not prove market entry, resolution, payout, Mainnet liquidity or official
NEAR Intents execution.

## If a judge wants independent verification

- Use the [proof ledger](PROOF.md) rather than repeating any transaction.
- Read the machine-readable evidence under [`docs/evidence/`](evidence/).
- Run the contract and Python regression commands in the [root README](../README.md#verification-commands).
- Run the frontend tests and production build from `web/`.
- Use the public API endpoints in the README's [API overview](../README.md#api-overview).

## Time-dependent and unavailable features

- The future Bitcoin market is intentionally not presented as settled.
- The deployed backend has no `NEAR_AI_KEY`; a missing or fallback research state
  is the correct result.
- A wallet is required for owner-bound Vault data and connected-wallet Portfolio
  reads, but no wallet action is needed to inspect the product.
- The temporary Cloudflare Quick Tunnel can rotate if its service restarts; the
  public demo depends on the current Vercel rewrite.
- Testnet assets have no value. Never give a judge a seed phrase, private key or
  instruction to fund a production wallet.
