# Phase 8B2 — Creator Subscriptions V1

Status: implemented as a Testnet-only vertical slice. No live transfer, deployment, signing, or backend key custody is part of this phase.

## Product contract

Verified creators can publish a versioned subscription plan covering one or more published premium research notes. The only supported terms are:

- 7 or 30 UTC days;
- one exact NEP-141 price in configured token base units;
- one configured Testnet payout account;
- one immutable plan terms version;
- one scope of published premium note IDs.

Authenticated readers manually purchase or renew through the existing 8B1 payment-intent flow. A subscription payment is never recurring: the reader must create a new intent and approve a new wallet transaction for every term.

Existing one-time entitlements remain independent. A verified one-time entitlement continues to unlock its purchased immutable note revision even when a subscription expires or the note is withdrawn. Subscription access is time-bound and is checked server-side on every protected premium request.

## Persistence and invariants

`CreatorNotesStore` adds durable records for:

- `creator_subscription_plans`: current status and current terms version;
- `creator_subscription_plan_versions`: append-only plan terms history;
- `creator_subscriptions`: one subscriber/plan relationship with UTC start/expiry and cancellation state;
- `creator_subscription_payments`: one verified finalized payment and granted term per intent.

Payment intents now carry `payment_kind`, plan/version, subscription ID, immutable terms JSON, and a correlation ID. Unique intent and transaction checks plus the store transaction prevent duplicate grants during retries or concurrent callbacks.

Before an active plan or intent is created, the server rechecks:

- authenticated creator ownership and verified session;
- configured `.testnet` NEP-141 metadata;
- payout account authorization and token storage registration;
- buyer token balance and positive NEAR gas balance;
- published premium scope and exact base-unit price.

A plan edit that changes title, description, duration, price, or scope creates a new terms version. Existing paid subscriptions retain the version they paid for; a renewal uses the current active plan version.

## Finalized payment path

The reader wallet is the only signer and broadcaster:

1. `POST /api/research/plans/{plan_id}/payment-intents` creates a server-bound subscription invoice.
2. The UI shows token contract, amount, recipient, memo, gas, duration, and the no-recurring-payment disclosure.
3. The reader explicitly approves the `ft_transfer` call in a Testnet wallet.
4. The reader submits the transaction hash to `POST /api/research/payment-intents/{intent_id}/verify`.
5. The server reads finalized transaction and block evidence and checks signer, token contract, recipient, amount, memo, successful receipt, NEP-141 event, final block, replay protection, and intent correlation.
6. Only the atomic subscription grant records a verified payment and UTC term. Failed or pending evidence grants no access.

No private key, signing capability, transfer broadcast, or Mainnet token is accepted by the subscription service.

## API surface

Public:

- `GET /api/research/plans`
- `GET /api/research/plans/{plan_id}`
- `GET /api/creators/{account_id}/plans`

Authenticated creator:

- `GET /api/research/plans/mine`
- `POST /api/research/plans`
- `POST /api/research/plans/{plan_id}/update`
- `GET /api/research/subscriptions` — creator and subscriber views

Authenticated reader:

- `POST /api/research/plans/{plan_id}/payment-intents`
- `GET /api/research/subscriptions`
- `GET /api/research/subscriptions/{subscription_id}`
- `POST /api/research/subscriptions/{subscription_id}/cancel`
- existing payment-intent verification and premium-content routes

Cancellation disables future renewal only. It does not revoke an already-paid active UTC term.

## UI surface

- Discover lists active plans without premium bodies.
- The plan detail page displays duration, exact Testnet token price, covered notes, current access, expiry, manual renewal, cancellation, and finalized-hash verification.
- Creator Studio supports creating plans, editing terms into a new version, activating/deactivating plans, selecting published premium notes, viewing subscriber counts, and reviewing verified subscriber payment history.
- All wallet approvals are explicit and identify the recipient, token contract, amount, memo, gas, and non-recurring Testnet behavior.

## Verification

Focused backend checks:

```text
python -m unittest services.creator_notes.tests.test_subscriptions services.web_api.tests.test_phase8b2_api
```

Frontend checks run from `web` because the repository root has no package manifest:

```text
cd web
npm run build
npm run lint
```

The subscription tests use explicitly mocked finalized NEAR receipts. They cover plan versioning and owner checks, active access, expiry, renewal, cancellation, withdrawn scope behavior, one-time entitlement preservation, and concurrent callback idempotency. The HTTP test covers public plan redaction, protected access, plan ownership, purchase verification, subscriber listing, and cancellation.

Browser screenshots/E2E and real Testnet wallet validation remain pending until a Playwright/Chromium harness and an approved disposable Testnet wallet are available.

## 8B3 handoff

Possible next work should remain separate from this slice:

- creator analytics and payout reconciliation;
- richer plan discovery/filtering and subscriber notifications;
- optional grace-period UX without changing server-side expiry rules;
- a separately approved subscription product experiment only after deciding whether a future contract, custody, or recurring-payment system is in scope.

Do not infer recurring billing, Mainnet support, automatic retries, refunds, or backend signing from this V1 implementation.
