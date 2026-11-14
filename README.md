# Notch

**Evidence-driven prediction intelligence for NEAR.**

Notch helps forecasters move from noisy attention signals to explicit,
source-backed prediction rules, verified market state, private research, and
safe paper-only agent workflows. It is a NEAR Testnet project. Test collateral
has no value.

## Who it helps

- **Forecasters** who want a transparent rule and evidence trail instead of an
  unexplained signal.
- **Research creators** who need owner-bound private theses and optional public
  research publishing.
- **Judges and operators** who need deterministic replay, finalized-chain
  verification, and honest failure states.

## What is implemented

- NEAR Testnet prediction markets with NEP-141 collateral entries, pooled
  payouts, resolution, claim and void/refund accounting.
- Forecast Passport classification for pending, correct, incorrect, voided and
  unknown predictions.
- Scout, Trend Radar, deterministic S3B attention oracle, Market Analyst and
  Research Council surfaces.
- Strategy Builder, Strategy Lab and Evaluation Lab.
- Private Research Vault using verified NEP-413 wallet ownership. Vault data is
  owner-restricted application storage, not end-to-end encryption.
- Agent Arena and audited browser-local Paper Autopilot. These do not sign,
  broadcast, trade, or move tokens.
- Wallet-scoped finalized-market notification inbox for resolved, claim-ready
  and refund-ready states. V1 reconciles safely when an authenticated user
  returns; it has no background worker yet.
- Creator research publishing and premium-access V1.
- Tidepool Testnet cross-chain funding discovery and verified funding evidence.

## Why NEAR matters

NEAR provides the finalized Testnet state used to verify market rules, outcomes,
positions, claimability and wallet ownership. The market contract uses NEP-141
collateral and NEP-413 signatures are used for owner-bound application sessions.
The API performs read-only finalized RPC calls for public state and notification
reconciliation; Notch does not receive private keys or seed phrases.

## Architecture

```text
web/                         React + TypeScript + Vite judge surface
  └─ authenticated API calls, Passport, Vault, Arena, Autopilot, inbox
services/web_api/            stdlib HTTP API and finalized-chain read boundary
services/creator_notes/      NEP-413 identity, Vault and creator research
services/near_ai/            grounded prompts, validation, provenance, fallback
services/research_council/  deterministic/evidence-backed council orchestration
services/trend_radar/       Scout and source-backed attention candidates
services/oracle/             frozen S3B rules and evidence receipts
services/intents/            Tidepool Testnet funding adapter
contracts/market/            Rust NEAR market contract
var/                         ignored local databases, fixtures and runtime data
```

The backend owns server-only credentials and persistent SQLite state. The
frontend must never receive `NEAR_AI_KEY`, Tidepool credentials, wallet keys or
session secrets.

## Run locally

Python services use the standard library. Node dependencies are required for the
frontend.

```bash
# Backend configuration; keep the resulting .env local and untracked
copy .env.example .env                 # Windows
# cp .env.example .env                 # macOS/Linux

python -m services.web_api.cli --host 127.0.0.1 --port 8020
```

In a second terminal:

```bash
cd web
npm ci
npm run dev -- --host 127.0.0.1 --port 5180
```

For local verification, configure a reliable finalized NEAR Testnet RPC in
`NEAR_RPC_URL`. The archived browser proof used FastNear archival RPC when the
default public RPC was rate-limited.

## Environment variable names

Values are intentionally omitted. Server-side names include:

```text
NEAR_RPC_URL
MARKET_CONTRACT
COLLATERAL_TOKEN
NEAR_NETWORK
WEB_API_HOST
WEB_API_PORT
WEB_API_CORS_ORIGINS
WEB_API_REQUEST_TIMEOUT_SECONDS
RADAR_DB_PATH
ORACLE_DB_PATHS
AI_BRIEFS_DATA_DIR
NEAR_AI_BASE_URL
NEAR_AI_KEY
NEAR_AI_MODEL
TIDEPOOL_BASE_URL
TIDEPOOL_API_KEY
CREATOR_NOTES_DB_PATH
RESEARCH_COUNCIL_DB_PATH
NOTIFICATIONS_DB_PATH
WEB_API_SNAPSHOT_DB
PULSE_DB_PATH
```

Frontend names are safe public configuration only:

```text
VITE_API_BASE
VITE_SITE_URL
VITE_MARKET_CONTRACT
```

## Tests and checks

```bash
# Python service tests
python -m unittest discover -s services/trend_radar/tests -t .
python -m unittest discover -s services/oracle/tests -t .
python -m unittest discover -s services/intents/tests -t .
python -m unittest discover -s services/near_ai/tests -t .
python -m unittest discover -s services/web_api/tests -t .

# Frontend typecheck/build and lint
cd web
npm run build
npm run lint

# Focused frontend tests
node --experimental-strip-types --test tests/research.test.mjs
node --experimental-strip-types --test tests/arena.test.mjs
node --experimental-strip-types --test tests/autopilot.test.mjs
node --experimental-strip-types --test tests/notifications.test.mjs
```

## Honest limitations

- NEAR Testnet only. Test tokens have no value.
- The current open Bitcoin market is unresolved and must remain pending until
  its legitimate resolution eligibility. No current-wallet payout is claimed.
- NEAR AI Cloud model discovery and a small JSON diagnostic succeeded, but full
  grounded research remains blocked by GLM reasoning-token exhaustion. The
  application preserves deterministic, source-only fallback and labels it as
  such. `LIVE_AI_VERIFIED` does not prove TEE or confidential-computing
  attestation.
- Agent Arena and Paper Autopilot are deterministic/browser-local paper
  workflows. They do not perform autonomous real-token trading.
- Notification reconciliation is on-return only. SQLite must be on durable
  backend storage; Vercel serverless filesystem storage is not sufficient.
- Tidepool evidence is community-operated Testnet sandbox evidence, not proof of
  official NEAR Intents Mainnet execution.
- Private Vault privacy is application authorization, not cryptographic
  encryption or anonymity.
- No email, Telegram, push, live settlement automation or production deployment
  is included.

## Verified evidence and demo

- [Hackathon demo walkthrough](docs/HACKATHON_DEMO_WALKTHROUGH.md)
- [Phase 7D cross-chain funding](docs/PHASE_7D_CROSS_CHAIN_FUNDING.md)
- [Phase 7D evidence JSON](docs/evidence/phase7d_base_sepolia_near_success_20261114.json)
- [Phase 6 Arena → Paper Autopilot browser proof](docs/evidence/phase6_agent_arena_autopilot_browser_20261114.json)
- [Wallet notifications V1](docs/NOTIFICATIONS_V1.md)
- [S2.5 historical market verification](docs/S2_5_ONCHAIN_VERIFICATION.md)
- [NEAR AI verification and fallback contract](docs/S5_NEAR_AI_VERIFICATION.md)
- [Frontend integration contract](docs/FRONTEND_INTEGRATION_CONTRACT.md)

The demo uses historical replay evidence separately from the unresolved future
market. Historical claims demonstrate settlement mechanics only; they are not
attributed to the current funded wallet.

## Repository status

The intended GitHub publication is a private repository until the contents and
preview deployment are reviewed. Public frontend deployment requires a stable
HTTPS backend with durable storage, finalized RPC access, CORS and authenticated
session configuration. Vercel is suitable for the existing `web/` frontend, not
for the stateful Python API or SQLite notification/Vault databases.
