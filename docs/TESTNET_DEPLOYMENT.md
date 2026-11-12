# Notch testnet deployment — S2.5 status

Date: 2026-11-11 (UTC), updated 2026-11-12 (UTC)
Network: NEAR testnet only. No real funds.

> **2026-11-12 update:** S3B is implemented and its two replay markets were
> created, funded, closed, resolved and claimed on 2026-11-12. This document
> keeps the earlier AI-forecast preparation as historical record. The current
> S2.5 demonstration is the S3B Nvidia Trend Trading replay and
> Bitcoin-vs-ChatGPT Trend Battle replay in
> [`docs/S2_5_ONCHAIN_VERIFICATION.md`](S2_5_ONCHAIN_VERIFICATION.md). The old
> AI-forecast rule hash must not be reused with S3B.
>
> **2026-11-12 short-window execution:** The initial replay timings (close
> 2026-11-15T23:59Z, resolve 2026-11-17T12:00Z) were unsuitable for the
> 2026-11-14 submission deadline. The executed 90-minute rules are
> `s3b-short-trend-nvidia-20261112T040029Z` and
> `s3b-short-battle-btc-chatgpt-20261112T040029Z`, entry
> 04:00:29Z–05:30:29Z, resolution eligible 05:35:29Z on 2026-11-12. Rule hashes
> are `sha256:79c8f464…` and `sha256:b6a5c889…`; evidence digests are
> `sha256:583eac07…` and `sha256:ad15ea91…`. Both markets resolved and claims
> settled before 05:40Z. See section 7 and
> [`docs/S2_5_ONCHAIN_VERIFICATION.md`](S2_5_ONCHAIN_VERIFICATION.md) section 11.
> No transaction is pending.

## Status summary

| Item | Status |
| --- | --- |
| S2 market contract deployed | **Yes** — `market.notch-dev.testnet` |
| Deployed code matches S2 artifact | **Yes** — byte-for-byte |
| Tidepool USDC collateral verified | **Yes** — `usdc.tidepool-sandbox.testnet`, 6 decimals |
| Market contract registered with USDC | **Yes** |
| Development wallet registered with USDC | **Yes** |
| S3B oracle | Implemented and locally verified; 65 S3B tests passing |
| S3B replay markets | **EXECUTED — both short-window markets created, resolved and claimed** |
| Current market count | **2** |
| First Trend Trading (AI forecast) market | **No — historical plan superseded by S3B replay shortlist** |
| Development wallet USDC balance | **100,000,000** base units (100 test USDC; restored after claims) |
| First position | **Placed — 1 test USDC on each winning side** |
| Onchain resolution / claim | **EXECUTED — UP and Bitcoin; 1 test USDC claimed per market; duplicate claim rejected** |
| Transactions submitted by S2.5 | **10 successful + 1 expected duplicate-claim rejection** |

## 1. Contract deployment evidence

| Field | Value |
| --- | --- |
| Contract account | `market.notch-dev.testnet` |
| Deployed code hash | `BGauRHWiPwFCbqrXJSzSAYG1bGVyMUidSxEvkionp1LK` |
| Deployed code size | 451,574 bytes |
| Deployed code SHA-256 | `9892eaa0c113378ca188137d6565d444ff6a8794bda3a596ce1fdcbb692f0f08` |
| Local S2 artifact | `contracts/market/res/notch_market.wasm` — same size and SHA-256 |
| Deployment transaction | `EFJvJVmBMWAh4Rqaxh7s2uCn72Hm1uXV3yc9zmEaEeDj` |
| Deployment block | 277,281,468 at 2026-11-11T23:15:40Z |
| Init call | `new({"owner":"notch-dev.testnet","operator":"notch-dev.testnet","resolver":"notch-dev.testnet","collateral_token":"usdc.tidepool-sandbox.testnet","min_entry_amount":"1000000"})` |
| USDC registration tx | `7bCin9AdmyG4zGVnfATrDXe1fmjZ1aUut9tCpFHgARX3` |
| USDC registration block | 277,281,905 at 2026-11-11T23:20:05Z |
| USDC registration call | `storage_deposit({"account_id":"market.notch-dev.testnet","registration_only":true})`, 0.00125 NEAR |
| Contract account balance | ~6.9965 NEAR |
| Contract storage usage | 451,928 bytes |

The deployment transaction carries a 32-byte `DeployContract` value equal to
the SHA-256 digest of the S2 wasm
(`9892eaa0c113378ca188137d6565d444ff6a8794bda3a596ce1fdcbb692f0f08`), which
base58-encodes to the account's `code_hash`. The account's full code was fetched
via `view_code` and hashes to the same value, so the deployed contract is the S2
artifact.

`notch-init.json` is the exact init argument file used for the deployment.

## 2. Onchain configuration readback

Read at block ~277,283,190:

```json
{
  "owner": "notch-dev.testnet",
  "operator": "notch-dev.testnet",
  "resolver": "notch-dev.testnet",
  "collateral_token": "usdc.tidepool-sandbox.testnet",
  "min_entry_amount": "1000000",
  "entries_paused": false,
  "market_count": 0,
  "fee_bps": 0
}
```

- `min_entry_amount` = 1,000,000 base units = **1 test USDC** (6 decimals).
- `get_market_count` = `0` at block 277,283,196.
- The proposed market ID did not exist (`get_market` returned `null`).
- `get_contract_config`, `get_market_count` and token storage were also read
  through `near-cli-rs 0.31.1`; the CLI output matched the RPC reads.

## 3. Development wallet readiness

| Item | Value |
| --- | --- |
| Account | `notch-dev.testnet` |
| NEAR balance | **2.9900126561431549 NEAR** |
| Access key | 1 full-access key (`ed25519:GPaX6TyNa9XiFy64rSpSKTbBq6opDA5ohD6XDoLfCG9v`) |
| USDC storage registration | Registered; total 0.00125 NEAR, available 0 |
| USDC balance | **0** |

The Tidepool faucet rejected this wallet because the account was less than
three hours old. Do not attempt to bypass the faucet rules. The account must age
past the restriction and then claim test USDC once through
<https://app.usetidepool.tech/faucet>. Test tokens have no value.

No private keys, seed phrases or credential files are recorded in this
repository or this document. The signer is accessed only through the local
`near-cli-rs` keychain.

## 4. First market proposal (historical AI forecast plan)

> This section is the earlier AI-forecast preparation. It is preserved for
> audit but is **not** the current S2.5 demonstration. Do not reuse the
> `sha256:a35c5ca6…` rule hash with the S3B oracle.

The first market is a **future forecast**, not a historical replay. The
observation window starts after entries close, so no pageview measurements are
known or committed at creation time.

| Field | Value |
| --- | --- |
| Market ID | `forecast-ai-attention-20261114-20261121` |
| Mode | `trend_trading` |
| Question | FORECAST (not a replay): Will daily en.wikipedia.org pageviews for `Artificial_intelligence` grow by at least 15.00% on the full UTC day 2026-11-21 versus the full UTC day 2026-11-14? (Wikimedia Pageviews, all-access, user) |
| Choices | `UP`, `DOWN` |
| Source ID | `wikimedia-pageviews-v1` |
| Source | Wikimedia Pageviews API, `en.wikipedia.org`, article `Artificial_intelligence`, `all-access` / `user`, daily, UTC |
| Baseline day | 2026-11-14 (full UTC day) |
| Target day | 2026-11-21 (full UTC day) |
| Formula | `growth-bps-v1`: `floor((target_views - baseline_views) * 10000 / baseline_views)` |
| Threshold | 1,500 bps (15.00%) — UP if growth ≥ threshold, otherwise DOWN |
| Minimum baseline | 1,000 views |
| Missing/partial data | VOID and refund |
| Invalidation policy | `refund_on_void` |
| Entry opens | 2026-11-12T00:00:00Z (`1794441600000000000` ns) |
| Entries close | 2026-11-13T23:59:00Z (`1794614340000000000` ns) |
| Resolution eligible | 2026-11-23T12:00:00Z (`1795435200000000000` ns) |
| Rule hash | `sha256:a35c5ca6f0c0fe86f15d1512f96909f66a07ed1036608454fb43db16d0cfb350` |

Frozen files:

- Rule: [`docs/market-rules/forecast-ai-attention-20261114-20261121.json`](market-rules/forecast-ai-attention-20261114-20261121.json)
- Exact contract arguments: [`docs/market-rules/forecast-ai-attention-20261114-20261121-create-args.json`](market-rules/forecast-ai-attention-20261114-20261121-create-args.json)
- Canonical hash helper: [`scripts/canonical_json_hash.py`](../scripts/canonical_json_hash.py)

The S2 Trend Trading schema does not store an observation-window field
onchain. The dates, article, source query, formula, threshold and minimum
baseline are frozen by the `rule_hash` commitment and published in the rule
file. The contract stores the same question, source ID, rule hash and timing.

Why this window: entries close before the baseline day starts, so participants
cannot react to baseline data. The target day is a week later. Resolution is
eligible after the target day plus the Wikimedia publication buffer.

### Rule hash verification

```bash
python scripts/canonical_json_hash.py \
  docs/market-rules/forecast-ai-attention-20261114-20261121.json
# sha256:a35c5ca6f0c0fe86f15d1512f96909f66a07ed1036608454fb43db16d0cfb350
```

Canonical form is UTF-8 JSON with sorted keys and compact `,`/`:` separators,
hashed with SHA-256. The hash was independently recomputed with a second
Python expression and matched. The rule hash, question and timing were also
checked field-by-field against the contract argument file.

### Source validation

The article and API were validated read-only for 2026-11-01 through 2026-11-10
using an identified `NotchMarket/0.1` User-Agent. `Artificial_intelligence`
returned complete daily observations with 10,648–17,226 views/day on
`en.wikipedia.org`, `all-access`, `user`. `AI_agent` was rejected as a candidate
because its daily views were below the 1,000 minimum baseline.

No measurements for 2026-11-14 or 2026-11-21 exist yet; the market is a genuine
forecast.

## 5. Market creation preview — historical pre-execution record

The exact transaction was built and **signed successfully with the local
keychain but not broadcast**:

- Signer: `notch-dev.testnet`
- Receiver: `market.notch-dev.testnet`
- Method: `create_market`
- Arguments: exact file above
- Gas: 100 Tgas
- Deposit: 0 NEAR
- Signer public key: `ed25519:GPaX6TyNa9XiFy64rSpSKTbBq6opDA5ohD6XDoLfCG9v`
- CLI result: `Your transaction was signed successfully.`

No signed transaction or signature was persisted in the repository.

To create the market after explicit approval:

```bash
near contract call-function as-transaction market.notch-dev.testnet create_market \
  file-args docs/market-rules/forecast-ai-attention-20261114-20261121-create-args.json \
  prepaid-gas '100 Tgas' attached-deposit '0 NEAR' \
  sign-as notch-dev.testnet network-config testnet sign-with-keychain send
```

After sending, record the transaction hash here and verify:

```bash
near contract call-function as-read-only market.notch-dev.testnet get_market \
  json-args '{"market_id":"forecast-ai-attention-20261114-20261121"}' \
  network-config testnet now

near contract call-function as-read-only market.notch-dev.testnet get_market_count \
  json-args '{}' network-config testnet now
```

Expected: market count `1`, mode `trend_trading`, status `open`, the exact
question/choices/source/rule hash above, and zero totals.

## 6. First position procedure

The development wallet currently has **0 test USDC**, so no position can be
placed. Once the wallet is past the faucet age restriction:

1. Claim test USDC once at <https://app.usetidepool.tech/faucet> and wait for
   the transfer.
2. Verify the token balance:
   ```bash
   near contract call-function as-read-only usdc.tidepool-sandbox.testnet \
     ft_balance_of json-args '{"account_id":"notch-dev.testnet"}' \
     network-config testnet now
   ```
3. Deposit exactly the 1 USDC minimum into the market only while it is open:
   ```bash
   near contract call-function as-transaction \
     usdc.tidepool-sandbox.testnet ft_transfer_call \
     json-args '{"receiver_id":"market.notch-dev.testnet","amount":"1000000","msg":"{\"market_id\":\"forecast-ai-attention-20261114-20261121\",\"outcome\":0}"}' \
     prepaid-gas '100 Tgas' attached-deposit '1 yoctoNEAR' \
     sign-as notch-dev.testnet network-config testnet sign-with-keychain send
   ```
4. Verify:
   ```bash
   near contract call-function as-read-only market.notch-dev.testnet get_position \
     json-args '{"market_id":"forecast-ai-attention-20261114-20261121","account_id":"notch-dev.testnet"}' \
     network-config testnet now

   near contract call-function as-read-only market.notch-dev.testnet get_market_totals \
     json-args '{"market_id":"forecast-ai-attention-20261114-20261121"}' \
     network-config testnet now
   ```

The Tidepool faucet/swap and the market `ft_transfer_call` are separate
operations. A swap receipt is not a market position.

## 7. Current S2.5 replay settlement plan (short windows)

The initial replay rules closed 2026-11-15 and resolved 2026-11-17, after the
hackathon deadline. They are preserved for audit but superseded by these
90-minute rules generated from live chain time
`2026-11-12T03:58:29Z`:

| Market | Rule hash | Evidence digest | Result | Entry window | Resolve after |
| --- | --- | --- | --- | --- | --- |
| `s3b-short-trend-nvidia-20261112T040029Z` | `sha256:79c8f464a8cb4fe1c2cd42b636755c9d31c5ad87abe2bca84af3427ccb47d0a9` | `sha256:583eac071d0b3d8a9ad661f02180c2d1c58fbac435e68b5c6346a28348257e06` | UP | 2026-11-12T04:00:29Z–05:30:29Z | 2026-11-12T05:35:29Z |
| `s3b-short-battle-btc-chatgpt-20261112T040029Z` | `sha256:b6a5c88950744db167b02743ec5bab517d7dc0073911ef2dab478f55934c6e57` | `sha256:ad15ea91fa97e32cc97e5dd94dc5db72a511e5fa980b1e8c7615b2db0ccd3e5d` | TOPIC_A (Bitcoin) | 2026-11-12T04:00:29Z–05:30:29Z | 2026-11-12T05:35:29Z |

Source observations remain the complete 2026-11-03 and 2026-11-10 UTC days. The
questions explicitly say `HISTORICAL REPLAY (not a forecast)`. The new evidence
digests verify. Old long-window rules/evidence in
`var/oracle_live_final` are unchanged.

Exact create payloads:

- `docs/evidence/s2_5_short_create_args_trend_nvidia.json`
- `docs/evidence/s2_5_short_create_args_battle_bitcoin_chatgpt.json`

The markets were executed on 2026-11-12. All ten lifecycle transactions
succeeded; the final claim settled before 05:40Z.

| Step | Nvidia Trend Trading | Bitcoin/ChatGPT Trend Battle |
| --- | --- | --- |
| Create | `2k4v9StY83xsyqAkR36Zke92HxA6U6UbXejVZGDDNxdJ` | `2suiYW9xYGPPYiX3DpHuuQ7NAUrxGuTVxvyrctibvev8` |
| Deposit 1 test USDC | `CMLP8mVWgEZLHb2EXF29EXGSbvJjAbP9LSRC9WjVuXRB` | `6MSX3WrtgZ2pPAEr5McodeU9g8x3rq2Dkog7uRv9Nik6` |
| Close | `2q7oAYrCZN49n9PwKWXZNxhqxRQFef4z9jb9ytXzu7Xv` | `FrKG8vK1EN2FXWAgBDqPat7HmTa6AodRVxM4UdGTwd7X` |
| Resolve | `Bh7kDST6dhMDwz5gMfsjrmmmtpbZZsSvKkukjkGzL4u1` | `2tvcgQA4Y7wDHvFv3EaQ3WJNvwnsgZZLvyxfxm5hsqmH` |
| Claim | `C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr` | `C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU` |

Final balances: wallet `100000000`; market contract `0`. Final market totals
are `["1000000", "0"]` each with `paid_total = 1000000` and
`unclaimed_reserve = 0`. Full evidence is in
[`docs/S2_5_ONCHAIN_VERIFICATION.md`](S2_5_ONCHAIN_VERIFICATION.md) section 11
and `docs/evidence/s2_5_execution_20261112.json`.

## 8. Remaining limitations

1. **One-sided demonstration:** only the winning side was funded in each
   market. There was no opposing trader. Claims returned 1 test USDC of stake
   per market, proving collateral recovery and settlement mechanics, not profit.
2. **Historical replay:** the markets are labeled `HISTORICAL REPLAY (not a
   forecast)` and use the 2026-11-03 / 2026-11-10 Wikimedia observations.
3. **Testnet only:** Tidepool test USDC and NEAR testnet; no mainnet assets.
4. **No blockers** remain for the one-sided S2.5 demonstration. A two-party
   market remains a separate validation slice.
5. **Old long-window rules and AI-forecast rule** are preserved but superseded;
   do not reuse their hashes.

## 9. Explorer links

- Contract account: <https://explorer.testnet.near.org/accounts/market.notch-dev.testnet>
- Developer account: <https://explorer.testnet.near.org/accounts/notch-dev.testnet>
- Deployment transaction: <https://explorer.testnet.near.org/transactions/EFJvJVmBMWAh4Rqaxh7s2uCn72Hm1uXV3yc9zmEaEeDj>
- USDC registration transaction: <https://explorer.testnet.near.org/transactions/7bCin9AdmyG4zGVnfATrDXe1fmjZ1aUut9tCpFHgARX3>
- Collateral token: <https://explorer.testnet.near.org/accounts/usdc.tidepool-sandbox.testnet>
- Trend create: <https://explorer.testnet.near.org/transactions/2k4v9StY83xsyqAkR36Zke92HxA6U6UbXejVZGDDNxdJ>
- Battle create: <https://explorer.testnet.near.org/transactions/2suiYW9xYGPPYiX3DpHuuQ7NAUrxGuTVxvyrctibvev8>
- Trend resolve: <https://explorer.testnet.near.org/transactions/Bh7kDST6dhMDwz5gMfsjrmmmtpbZZsSvKkukjkGzL4u1>
- Battle resolve: <https://explorer.testnet.near.org/transactions/2tvcgQA4Y7wDHvFv3EaQ3WJNvwnsgZZLvyxfxm5hsqmH>
- Trend claim: <https://explorer.testnet.near.org/transactions/C4b882jAwpnZgo1ofHwAhQz55rFR7pjPyyGTMS1SD7pr>
- Battle claim: <https://explorer.testnet.near.org/transactions/C2sVEw9poAa9wqf4zGkkkXcrF1YxXw1yTPskBmoTntNU>

## 10. Completed actions and next milestone

1. Operator approval and local `approve-rule` for both short-window rules:
   completed 2026-11-12T04:22Z.
2. Both `create_market` calls broadcast and verified: completed.
3. Both 1 test USDC deposits accepted via `ft_transfer_call`: completed.
4. Both markets closed and resolved with S3B evidence: completed 05:37–05:38Z.
5. Both claims settled; duplicate claim rejected; balances reconciled:
   completed before 05:40Z.
6. All transaction hashes, evidence hashes and final state recorded in
   [`docs/S2_5_ONCHAIN_VERIFICATION.md`](S2_5_ONCHAIN_VERIFICATION.md) section 11
   and `docs/evidence/s2_5_execution_20261112.json`.

### Recommended next milestone

Run a **two-sided S2.6 market demonstration** with two distinct funded testnet
accounts to exercise both outcomes and the pooled payout split. After that, the
next product milestone is **S4 — Tidepool Intents testnet integration**, followed
by the **S5 consumer surface**. This S2.5 execution proves the contract and
oracle lifecycle; it does not prove a profitable two-party trade.
