# Phase 7D — Base Sepolia → NEAR Testnet funding proof

**Status: `DESTINATION_VERIFIED`**
**Scope: Testnet only; do not repeat this transfer.**

The first genuine Base Sepolia → NEAR Testnet funding transfer for the funded
Meteor account is preserved in
[`docs/evidence/phase7d_base_sepolia_near_success_20261114.json`](evidence/phase7d_base_sepolia_near_success_20261114.json).
The existing implementation and safety boundary remain documented in
[`docs/PHASE_7B_REAL_TESTNET_FUNDING.md`](PHASE_7B_REAL_TESTNET_FUNDING.md).

## Proof chain

- **Quote:** `f1085af2-5848-47e6-b9af-39ac86e2dec0`; provider status `SUCCESS`.
  The quoted input was `1.050000` test-USDC for `1.047270` output, with a
  `1.036797` minimum.
- **Source ERC-20 transfer:** Base Sepolia transaction
  [`0x39623909068e564ad2304091dbe1477688e5e51f4e908674ff219f84217c2d7b`](https://sepolia.basescan.org/tx/0x39623909068e564ad2304091dbe1477688e5e51f4e908674ff219f84217c2d7b)
  succeeded in block `58709487` at `2026-11-14T13:42:46Z`. The USDC
  `Transfer` receipt log records `1.500000` test-USDC from
  `0x51c63A4bcF8E622D686bF1D7ec5ae5b77D50E677` to the Tidepool deposit address
  `0x20c06F7615C4b7a3020d5AE0cCa85CA1d24A8809`.
- **Settlement:** Tidepool applied the quoted `1.050000` input, delivered
  `1.047270` test-USDC to NEAR, and refunded the excess `0.450000`.
- **Refund proof:** Base Sepolia transaction
  [`0x21acf175808d9c05b2b67dcee4b1dd18ebef0f73892037cd0411699b8145f49c`](https://sepolia.basescan.org/tx/0x21acf175808d9c05b2b67dcee4b1dd18ebef0f73892037cd0411699b8145f49c)
  succeeded in block `58709594` at `2026-11-14T13:43:07Z`. Its USDC receipt
  log records `450000` base units to the source wallet.
- **Independent NEAR verification:** the persistent observation
  `f1085af2-5848-47e6-b9af-39ac86e2dec0:pre-transfer` recorded `99,000,000`
  base units. At finalized block `277665477`
  (`EaViN3tNY5bf2S76jZBQSDT6CpkBGZVvDh2YqoowjQUM`), the recipient held
  `100,047,270` base units: delta `1,047,270`, above the required minimum.
  The Tidepool NEAR settlement transaction is
  [`8b5WKmEqBpVu8mLDAbKHmrDHEiJCZEwBkHYqbryPKfum`](https://testnet.nearblocks.io/txns/8b5WKmEqBpVu8mLDAbKHmrDHEiJCZEwBkHYqbryPKfum).
- **Intent provenance:**
  `GfYm9axF5ubakHrLt6K8uUMYTVD2cVVTNZki4MV2fR7n` and
  `Hiz36w7qTGgXtcuYwatazvQk3tyhWzeSKTNzY7kK9fnK`.

## Boundary

This proves a successful testnet funding transfer and the independently
measured NEAR balance increase. It does **not** prove market entry, oracle
resolution, keeper finalization, claiming, or production readiness. Tidepool is
a community-operated testnet sandbox; no mainnet asset or private key is used.
