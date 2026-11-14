# Phase 8A — Creator Studio & Verifiable Research Publishing V1

Phase 8A adds a source-backed, revisioned publishing surface for creator research notes. It does **not** add payments, monetization, token transfers, transaction signing, or smart-contract changes.

## Ownership verification

1. The browser requests `POST /api/research/identity/challenge` for the connected NEAR Testnet account.
2. The wallet signs the returned message through NEP-413 `signMessage`.
3. The API verifies the Ed25519 signature over the NEP-413 Borsh payload and performs a final `view_access_key` lookup for the claimed account.
4. A short-lived opaque bearer session is issued. Only a SHA-256 hash of the bearer token is stored in SQLite.

Notch never receives a private key, signs a transaction, broadcasts, or requests a token allowance. The V1 identity claim is deliberately narrow: control of an on-chain signing key at verification time. It is not a legal-name, personhood, editorial-quality, or human-authorship attestation.

## Note safety and provenance

A note is a versioned `notch.creator-research-note/1` record with:

- creator account and verification flag;
- title, thesis, position, and market/topic reference;
- supporting and contradictory evidence lanes;
- exact HTTPS source URLs, source IDs, observation timestamps, and an observation cutoff;
- deterministic content and evidence digests;
- optional local strategy/evaluation references preserved as `integrity: as_supplied`;
- immutable revision history and explicit `DRAFT`, `PUBLISHED`, and `WITHDRAWN` states.

Publication requires a verified session, a valid stored market or Radar topic reference, at least one supporting observation, supported source IDs, HTTPS URLs, and evidence no later than the note cutoff. Future observations are rejected; the service does not use lookahead data. Duplicate published content for the same creator is rejected. Withdrawal removes a note from public discovery while retaining the ledger for the creator.

The supported source catalog is intentionally bounded to genuine stored Wikimedia observations (`wikimedia-pageviews-v1` and Wikimedia observation IDs). Other Radar/market sources remain outside this V1 publication boundary. V1 does not fetch or independently re-attest arbitrary URLs at publication time; it validates the reference shape and records the submitted provenance exactly.

## API and storage

Public:

- `GET /api/research/notes?limit=...`
- `GET /api/research/notes/{note_id}`
- `GET /api/creators/{account_id}/notes?limit=...`

Identity and private authoring:

- `POST /api/research/identity/challenge`
- `POST /api/research/identity/verify`
- `GET /api/research/me`
- `GET /api/research/notes/mine`
- `POST /api/research/notes`
- `POST /api/research/notes/{note_id}/update`
- `POST /api/research/notes/{note_id}/publish`
- `POST /api/research/notes/{note_id}/withdraw`

SQLite is configured by `CREATOR_NOTES_DB_PATH` and defaults to `var/web_api/creator_notes.sqlite3`. The schema includes notes, immutable revisions, single-use challenges, and expiring sessions. `Authorization: Bearer` is allowed by the stdlib API server CORS boundary.

## UI

- `/app/studio` provides wallet verification, drafting, editing, publication, withdrawal, and a private revision ledger.
- `/app/discover` includes public Creator Research discovery.
- `/app/research/notes/{note_id}` provides public inspection of the thesis, evidence lanes, cutoff, source IDs, content/evidence digests, and revision history.

## V1 limitations / Phase 8B inputs

- The API remains local/persistent SQLite unless deployed behind a public HTTPS host.
- Sessions are bearer tokens held by the browser; production deployment should add origin policy, secure storage, revocation, audit/abuse controls, and operational secret management.
- V1 validates source references and cutoff ordering but does not re-fetch every submitted URL or create a third-party notarization.
- Local strategy/evaluation artifacts are referenced by exact supplied revision/result digests; V1 does not claim to verify browser-local files.
- There is no moderation, collaborative review, reputation, monetization, or social identity layer.
- Phase 8B should address deployed storage, public-origin smoke tests, session revocation, rate limits by verified account, content moderation, source revalidation, and a separately reviewed publication trust model.
