# Notch proof ledger

This ledger is intentionally conservative. Each row says what the evidence
establishes and what it does **not** establish. All chain evidence below is
Testnet or Base Sepolia testnet evidence; test assets have no monetary value.

**Verification pass:** 2026-11-14 UTC<br>
**Public app checked:** [notch-blond-psi.vercel.app](https://notch-blond-psi.vercel.app)<br>
**Market contract:** [`market.notch-dev.testnet`](https://testnet.nearblocks.io/address/market.notch-dev.testnet)<br>
**Collateral:** `usdc.tidepool-sandbox.testnet` (NEP-141, six decimals)

## Ledger

| Proof | Network | Verified evidence | What it establishes | What it does not establish |
| --- | --- | --- | --- | --- |
| Contract deployment | NEAR Testnet | [Deployment transaction `EFJvJ...`](https://testnet.nearblocks.io/txns/EFJvJVmBMWAh4Rqaxh7s2uCn72Hm1uXV3yc9zmEaEeDj); NEARBlocks indexed `DEPLOY_CONTRACT` and `new` to `market.notch-dev.testnet` in block `277281468` | The Rust market contract was deployed and initialized on NEAR Testnet | Mainnet deployment, production readiness or economic value |
| Future market creation | NEAR Testnet | [Create transaction `ALVPQ...`](https://testnet.nearblocks.io/txns/ALVPQpRCwngtpLPtG94SrXb9Y4jogaFToTzvGusveXDA); action `create_market` in block `277347610`; [live market detail](https://notch-blond-psi.vercel.app/app/markets/s3b-future-btc-20261116-20261123) | The Bitcoin forecast market exists with its locked rule and open state | A resolved outcome, valid future evidence or a claimable payout |
| Historical Nvidia lifecycle | NEAR Testnet | Create `2k4v9StY83xsyqAkR36Zke92HxA6U6UbXejVZGDDNxdJ`; deposit `CMLP8mVWgEZLHb2EXF29EXGSbvJjAbP9LSRC9WjVuXRB`; close `2q7oAYrCZN49n9PwKWXZNxhqxRQFef4z9jb9ytXzu7Xv`; resolve `Bh7kDST6dhMDwz5gMfsjrmmmtpbZZsSvKkukjkGzL4u1`; claim [`C4b882...`](https://testnet.nearblocks.io/txns/C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr) | One historical market completed create → deposit → close → resolve → claim; evidence hash and `UP` outcome matched the stored rule | Profit, two-sided liquidity, a current-wallet payout or a forward forecast |
| Historical Bitcoin/ChatGPT lifecycle | NEAR Testnet | Create `2suiYW9xYGPPYiX3DpHuuQ7NAUrxGuTVxvyrctibvev8`; deposit `6MSX3WrtgZ2pPAEr5McodeU9g8x3rq2Dkog7uRv9Nik6`; close `FrKG8vK1EN2FXWAgBDqPat7HmTa6AodRVxM4UdGTwd7X`; resolve `2tvcgQA4Y7wDHvFv3EaQ3WJNvwnsgZZLvyxfxm5hsqmH`; claim [`C2sVEw...`](https://testnet.nearblocks.io/txns/C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU) | A second historical battle resolved to Bitcoin and its one-sided stake was claimed | Profit, organic opposing activity or Mainnet settlement |
| Historical duplicate protection | NEAR Testnet | Failed duplicate claim `FEMWzAad5BWYGk8pHQKT87CfMqAUYj2qaoQzNtoMUHu4`; post-failure claimable remained `0` in [`S2_5_ONCHAIN_VERIFICATION.md`](S2_5_ONCHAIN_VERIFICATION.md) | Claim accounting rejects a second payout and preserves state | A general security audit or formal verification |
| Base Sepolia source transfer | Base Sepolia | [Source transaction](https://sepolia.basescan.org/tx/0x39623909068e564ad2304091dbe1477688e5e51f4e908674ff219f84217c2d7b); `eth_getTransactionReceipt` returned status `0x1`, block `58709487`; USDC Transfer log amount `1,500,000` | The source wallet sent `1.500000` test-USDC to the Tidepool deposit address | NEAR destination receipt, market entry or payout |
| Base Sepolia excess refund | Base Sepolia | [Refund transaction](https://sepolia.basescan.org/tx/0x21acf175808d9c05b2b67dcee4b1dd18ebef0f73892037cd0411699b8145f49c); receipt status `0x1`, block `58709594`; USDC Transfer log amount `450,000` | The provider refunded `0.450000` test-USDC to the source wallet | Mainnet bridge guarantees or a market-specific funding relationship |
| NEAR Tidepool settlement | NEAR Testnet | [Settlement transaction](https://testnet.nearblocks.io/txns/8b5WKmEqBpVu8mLDAbKHmrDHEiJCZEwBkHYqbryPKfum); `execute_intents` to `verifier.tidepool-sandbox.testnet` in block `277664546`; Phase 7D record measured `99,000,000 → 100,047,270` base units at finalized block `277665477` | A quoted `1.047270` test-USDC destination delta was observed and exceeded the quoted minimum | Official NEAR Intents Mainnet execution, market entry, resolution or claim |
| Current demo account position | NEAR Testnet | [Public Passport](https://notch-blond-psi.vercel.app/app/p/4c9c0572fedb185055adb0acce14c2cf0f8652f07f3500fba7bacd3dadfad2c0); public API returns the future market with `UP`, `claimable: 0`, `claim_state: open`, `prediction_status: PENDING` | The deployed read path reflects the documented account's current finalized position state | A resolved outcome or a current claimable payout |

The full machine-readable funding record is
[`evidence/phase7d_base_sepolia_near_success_20261114.json`](evidence/phase7d_base_sepolia_near_success_20261114.json).
The full historical lifecycle record is
[`evidence/s2_5_execution_20261112.json`](evidence/s2_5_execution_20261112.json).

## Future-entry transaction gap

The project walkthrough records the following future-market entry candidate:

```text
1JEFnWsuh2jWpYPZV957WgNFdwbv7kTTQ7GUs7t72oh
```

A direct NEARBlocks transaction endpoint lookup did not return a record during
this documentation pass, although the NEARBlocks account index for the
recipient account lists an `ft_transfer_call` in block `277527940` with receipt
`GpU5jZoAXduKaWeHHKV2VYb9nFJ3J16feW82abZ8KGV1`. The public API independently
returns the associated `UP` position and `PENDING` state.

**Label: not independently verified as a standalone explorer transaction in
this pass.** It is retained as secondary evidence, not used as the primary
settlement proof. The historical claim transactions above are the recommended
judge verification path.

## Authentication and API security proof

| Boundary | Evidence | Establishes | Does not establish |
| --- | --- | --- | --- |
| NEP-413 identity | [`services/creator_notes/identity.py`](../services/creator_notes/identity.py), [`services/creator_notes/tests/test_creator_notes.py`](../services/creator_notes/tests/test_creator_notes.py) | Challenge signing, Ed25519 verification, final access-key lookup and expiring bearer sessions | Legal identity, personhood or human authorship |
| Vault owner isolation | [`test_private_vault.py`](../services/web_api/tests/test_private_vault_api.py), [`services/creator_notes/tests/test_private_vault.py`](../services/creator_notes/tests/test_private_vault.py) | Missing auth returns `401 AUTH_REQUIRED`; records are filtered to the verified session owner; update/delete are owner-bound | Encryption, anonymity or database compromise resistance |
| Notification isolation | [`test_notifications.py`](../services/web_api/tests/test_notifications.py) | Wallet-scoped reads and read-state updates use the verified session; reconciliation reads finalized positions | Continuous delivery, push notifications or a background worker |
| API secret boundary | [`test_api.py`](../services/web_api/tests/test_api.py) | API responses and errors do not expose `Authorization` values or `NEAR_AI_KEY` | A full production penetration test |
| Public ingress | [public health endpoint](https://notch-blond-psi.vercel.app/api/health), [market API](https://notch-blond-psi.vercel.app/api/markets) | Vercel `/api` rewrite reaches the isolated Hermes API and returns live Testnet reads | Stable named HTTPS infrastructure; the current Quick Tunnel can rotate |

## Regression and browser evidence

The repository's relevant verification commands are:

```bash
cargo test -p notch-market

python -m unittest discover -s services/trend_radar/tests -t .
python -m unittest discover -s services/oracle/tests -t .
python -m unittest discover -s services/intents/tests -t .
python -m unittest discover -s services/near_ai/tests -t .
python -m unittest discover -s services/web_api/tests -t .

cd web
npm ci
npm run build
npm run lint
npm run test:research
npm run test:arena
npm run test:autopilot
npm run test:notifications
```

The bounded browser proof is
[`evidence/phase6_agent_arena_autopilot_browser_20261114.json`](evidence/phase6_agent_arena_autopilot_browser_20261114.json).
It records:

- deterministic Arena match `arena_match_935505c1`;
- strategy hash `fnv1a32:7d6d7c32`;
- browser-local policy `autopilot_cd51a888`;
- current published-market results `BLOCKED` with explicit audit IDs;
- a separate frozen-fixture `PAPER_EXECUTED` row;
- no wallet signing, token transfer, market write or chain state change.

## Not independently verified / not claimed

- The future Bitcoin market has no verified outcome yet.
- No current-wallet claim or refund is claimed.
- Full live NEAR AI research generation is not a reliable deployed capability;
  the backend has no `NEAR_AI_KEY`.
- `LIVE_AI_VERIFIED` is a provider/model diagnostic, not TEE or confidential
  computing attestation.
- The Quick Tunnel is temporary and has no stable DNS ownership.
- Testnet balances and claims are not monetary returns.
- No Mainnet contract, Mainnet collateral or official NEAR Intents Mainnet
  transfer is claimed.
