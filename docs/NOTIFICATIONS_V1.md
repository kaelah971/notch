# Wallet notifications V1

Status: implemented as a read-only, wallet-scoped inbox. No email, push,
Telegram, wallet signing, claim, refund, or chain write is performed.

## Detection boundary

`GET /api/notifications` requires the existing verified NEP-413 Creator Studio
session. The API derives the account from the bearer session; it never trusts an
account ID supplied by the caller.

On each authenticated inbox read, Notch performs a bounded **on-return**
reconciliation:

1. list the published market set;
2. read each candidate market and that wallet's position through finalized NEAR
   view calls;
3. ignore OPEN, CLOSED, invalid, or non-final observations;
4. create durable alerts only for a real position and a verified resolved/voided
   state;
5. deduplicate by wallet, notification type, market, and immutable resolution
   marker.

There is no background worker in V1. A user who is away is reconciled the next
time their authenticated inbox is opened or refreshed. Each notification stores
finality, observation time, market block height/hash, and position block
height/hash when the RPC supplies them.

## Notification types

- `MARKET_RESOLVED`: finalized market outcome plus the wallet's classified
  prediction status.
- `CLAIM_READY`: only when the finalized position reports `claim_state=claimable`
  and a positive claimable balance.
- `REFUND_READY`: only when the finalized market is `voided` with `void` or `tie`
  resolution and the position reports a positive claimable balance.

The future Bitcoin market remains OPEN and cannot create a resolution or claim
alert from a deadline alone.

## Storage and deployment

Notifications are stored in SQLite at `NOTIFICATIONS_DB_PATH`, defaulting to
`var/web_api/notifications.sqlite3`. The database must live on durable shared
backend storage for public deployment. Vercel serverless filesystem storage is
not a suitable production notification store. No database migration is
performed by the frontend deployment.

## Demonstration

`/app/notifications` includes a clearly labeled, UI-only preview of the verified
historical Nvidia replay. The preview is not persisted, not tied to a wallet,
and cannot trigger a claim. Real inbox rows are available only after wallet
ownership verification through the existing Vault/NEP-413 flow.
