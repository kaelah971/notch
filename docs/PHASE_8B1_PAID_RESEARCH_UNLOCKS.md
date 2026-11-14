# Phase 8B1 — Paid Research Unlocks V1

Phase 8B1 adds a Testnet-only, receipt-verified unlock for an immutable premium research-note revision. It does not add subscriptions, recurring charges, creator earnings, royalties, referrals, Mainnet payments, or backend key custody.

## Authentication and payout boundary

The existing Phase 8A NEP-413 flow remains the only identity boundary. Sessions are short-lived bearer tokens whose SHA-256 hashes are stored in SQLite. The server rechecks the authenticated public key against the final NEAR Testnet access-key view before configuring a payout account.

V1 deliberately restricts the payout account to the currently authenticated creator account. The frontend cannot choose an arbitrary recipient. The configured token is the existing NEAR Testnet collateral token, and configuration requires verified NEP-141 metadata plus a non-null `storage_balance_of` result for the creator account.

## Premium note model

A note revision may include:

- public title, thesis, evidence lanes, cutoff, provenance and performance disclosures;
- a private premium body and body digest;
- an exact integer base-unit price captured with the revision;
- the verified Testnet token contract, symbol and decimals.

Public list/detail/creator-profile responses include only the offer metadata and `locked: true`; they never include premium text. The authenticated creator may see their own premium draft. A buyer receives only the exact purchased revision through the authenticated premium endpoint.

Changing the body or price creates a new immutable note revision. Existing public preview/evidence remains public; V1 never claims that previously exposed content became confidential.

## Payment intent lifecycle

`POST /api/research/notes/{note_id}/payment-intents` creates a durable invoice containing the authenticated buyer, creator payout account, note revision and digest, fixed Testnet token, integer amount, unique memo, creation/expiry timestamps and `PENDING` status. Before creating it, the server reads the buyer's configured-token balance and native NEAR balance; insufficient token funds or a zero gas balance is rejected. It returns an exact `ft_transfer` action with a 1 yocto deposit and 30 TGas for explicit wallet approval.

The browser may submit a transaction hash to `POST /api/research/payment-intents/{intent_id}/verify`, but the hash is never treated as proof. The server calls finalized NEAR Testnet transaction status and requires:

1. successful transaction status;
2. transaction signer equal to the authenticated buyer;
3. token contract as the transaction receiver;
4. an `ft_transfer` action with the exact verified recipient, amount and invoice memo;
5. successful token receipt execution in a finalized block;
6. a matching `nep141` `ft_transfer` event with exact sender, recipient and amount;
7. transaction evidence not already attached to another intent.

Pending finality remains `PENDING`. Failed, underpaid, wrong-recipient, wrong-token, wrong-memo, malformed or replayed evidence never grants access. SQLite uniqueness plus an idempotent entitlement insert make duplicate callbacks and concurrent verification safe.

## Access rules

- The creator can read the current premium revision for their own note through the authenticated endpoint.
- A buyer can read only a revision for which a durable entitlement exists.
- A buyer's entitlement points to the exact immutable note revision and content digest purchased.
- Public and unauthenticated requests receive previews only.
- Logout/login and reload do not erase entitlements; server-side account identity and SQLite records remain authoritative.

## Endpoints

- `GET /api/research/payout`
- `POST /api/research/payout/configure`
- `GET /api/research/notes/{note_id}/premium` (authenticated)
- `POST /api/research/notes/{note_id}/payment-intents`
- `GET /api/research/payment-intents/{intent_id}`
- `POST /api/research/payment-intents/{intent_id}/verify`
- `GET /api/research/purchases`

The premium route is intentionally server-authorized. Browser storage, hidden fields, transaction popups and local UI state cannot unlock content.

## Phase 8B2 handoff

The durable intent/entitlement model is ready to extend with reviewed terms for:

- fixed-term creator subscriptions;
- expiring entitlements and manual renewal;
- creator subscription offerings and pricing revisions;
- cancellation, expiry and grace-period rules;
- payment disputes, refunds and reconciliation.

8B2 must add explicit entitlement expiry semantics, subscription-specific ledger states, cancellation/refund policy, reconciliation tooling and abuse controls. It must not introduce unattended recurring charges without a separately approved wallet/authorization model. No recurring or subscription behavior is implemented here.

## Verification status

The implementation tests use explicitly labelled mocked finalized receipt payloads. No Testnet token transfer was initiated during this implementation run, and no real purchase or unlock is claimed.
