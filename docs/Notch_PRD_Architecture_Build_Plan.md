---
title: "Notch | PRD, architecture and build plan"
brand: "Notch"
descriptor: "Evidence-led attention markets"
status: "Planning / not yet deployed"
source_basis: "Editable Markdown replacement derived from the supplied PRD, architecture and build-plan PDF"
date: "11 November 2026"
---

# Notch | PRD, architecture and build plan

> **Brand:** Notch  
> **Descriptor:** Evidence-led attention markets  
> **Status:** Planning / not yet deployed  
> **Source fidelity:** The technical requirements below preserve the supplied PRD and build-plan content. The original PDF remains unchanged.

## Document control

This document is the editable Markdown replacement for the supplied technical specification. It covers end-to-end requirements, concrete market mechanics, ownership boundaries, contract interfaces, data policy, privacy, test strategy and the 11–14 November 2026 build sequence.

### Claim status

- **Shipped:** No deployed repository or exercised implementation was supplied for this engagement.
- **Target:** Requirements and integrations specified for the hackathon build.
- **Roadmap:** Features explicitly deferred beyond the hackathon core.
- **Hypothesis:** Product and positioning assumptions that still require validation.

### Name migration

The selected product identity is **Notch**. Product-facing titles, prose, repository layout and demo references use Notch. The supplied PDF remains the source artifact and has not been edited.

## Source page 1
02 / BUILD BLUEPRINT
### PRD and architecture
Requirements, smart contracts, oracle design, integrations,
privacy, test coverage and the 11-14 Nov execution plan.
NEAR Hackathon 2026  /  Research and product planning
11 November 2026  |  Notch brand locked for this editable replacement
NEAR TESTNET FIRST


## Source page 2
CONTROLLED BUILD SPECIFICATION
PRD, technical architecture and execution plan
This is the engineering handoff for the NEAR Hackathon Notch. It covers
end-to-end requirements, concrete market mechanics, ownership boundaries, contract
interfaces, data policy, privacy, test strategy and the build sequence from 11-14 November 2026.
DOCUMENT CONTROL
Status: planning / not yet deployed. Brand: Notch. Network: NEAR testnet. Primary track: Unstoppable
DeFi. Secondary: Open Innovation. Privacy & Private AI only if genuine verifiable functionality ships. Source of truth: actual
repository and deployed contract once implementation begins.
#### Decision register
ID
DECISION
STATE
ADR-01
Use one core contract for both market modes.
Locked
ADR-02
Pooled, fully collateralized binary positions; no leverage, no fees at MVP.
Locked
ADR-03
NEAR testnet settlement; NEP-141 test-token collateral.
Locked
ADR-04
Tidepool is a testnet Intents-compatible sandbox; official 1Click read-only quotes are separate.
Locked / verify live
ADR-05
Wikimedia pageviews is the primary data-oracle candidate; source policy reviewed before
activation.
Provisional
ADR-06
YouTube/Google offer permitted research context, not default market payouts.
Locked
ADR-07
Private watchlists in P1; sealed positions in P2; confidential funding V2.
Locked
ADR-08
AI explains evidence and never controls outcome or payouts.
Locked
ADR-09
First market creation and resolution are operator-gated.
Locked for MVP
### 1 Product goals, exclusions and success criteria
#### Goals
- Two market creation types with identical escrow and payout primitives.
- Real NEAR testnet collateral deposits, settlement and verified claims.
- Explicit evidence lineage from licensed/free data source to deterministic resolution.
- One end-to-end Intents-compatible testnet funding transaction.


## Source page 3
- Consumer UX including market discovery, wallet connection, portfolio, proof and share links.
- NEAR AI briefs and private research if key/credits and P0 performance permit.
#### Out of scope for hackathon MVP
- Real-money mainnet contracts, real payments, leverage, liquidation, perpetuals, options.
- Permissionless market creation or crowdsourced oracle voting.
- Claiming private financial transactions without cryptographic guarantees.
- Cross-platform blended social index without policy and manipulation review.
- Permanent production guarantees, audited smart contracts or licensed financial services.
#### Acceptance outcomes / KPIs
MEASURE
TARGET / TEST
End-to-end verified flows
At least 1 successful enter -> close -> resolve -> claim for each of the 2 market modes.
Intents proof
At least 1 completed Tidepool quote/deposit/settlement/status flow with explorer evidence.
Market integrity
Zero double claims, negative balances or excess payouts in automated tests.
Reproducibility
Fresh environment can replay README "do X, see Y" steps.
UX
Mobile and desktop market pages work with clear disconnected, loading, failure and pending
states.
Evidence
At least 2 market receipts link to exact data, rule, result and testnet transaction.
### 2 Personas, journeys and screen map
#### Core user journeys
01 New visitor opens a shared market URL -> reads metric definition -> connects NEAR testnet wallet -> obtains test
USDC -> enters a position.
02 Trader views Portfolio -> sees pending and resolved positions -> reads proof receipt -> clicks Claim -> checks
transaction on explorer.
03 Explorer opens a trend -> reads sourced NEAR AI brief -> compares related Trend Trading / Trend Battle
opportunities -> shares market.
04 Research user creates a private watchlist -> saves a note -> returns in another session without the information
appearing in public market data.
05 Operator seeds a market -> freezes baseline -> captures final observation -> runs deterministic resolver ->
submits the evidence hash and outcome.


## Source page 4
#### Information architecture
ROUTE / VIEW
REQUIRED COMPONENTS
/
Positioning hero; featured markets; how settlement works; privacy and testnet notices.
/markets
Type filters, topic categories, state OPEN/CLOSED/RESOLVED, sort by close time.
/markets/[id]
Question, source, formula, baseline, clock, pool totals, enter control, trend chart, brief, receipts.
/battles
Two-topic cards and normalized growth comparison; same position entry component.
/portfolio
Balance, open/closed/claimable positions, claim status, explorer links.
/fund
Faucet explanation, Tidepool swap initiation, status, refunds; separate official quote preview.
/trends/[slug]
NEAR AI brief, citations, observations and relevant markets.
/research
Owner-only watchlists and notes, access denied to other users.
/proof/[marketId]
Frozen market config, observations, calculation, signature/hash and transaction references.
#### Product state and error behavior
- Never show a live position price if the market uses pooled shares; show current pool split and estimated payout if the
pool closed now.
- Wallet disconnected -> show Connect Wallet; connected but zero test collateral -> Get Test USDC.
- Pending ft_transfer_call -> show transfer pending, query chain, prevent duplicate submit.
- Market missing observation -> show Awaiting Data, not fabricated resolution.
- Resolved -> show winning side, calculation, claim eligibility and receipt.
- Void -> show the declared reason and refundable contribution.
- Tidepool errors -> separate QUOTE_EXPIRED, PENDING_DEPOSIT, INCOMPLETE_DEPOSIT, FAILED,
REFUNDED and SUCCESS where supported.
### 3 Product requirements - functional specification


## Source page 5
#### Market discovery and trading
ID
REQUIREMENT
ACCEPTANCE TEST
FR-01
Display curated trend topics and market list with filter by mode
and status.
A visitor can navigate both market types without signing in.
FR-02
Show immutable market question, data source, time window,
threshold/battle rule and invalidation policy.
Details match contract/config snapshot.
FR-03
Connect supported NEAR testnet wallet and show correct
collateral balance.
No live-chain wallet is mislabeled testnet.
FR-04
Enter a side with NEP-141 test token through validated
transfer-and-call.
Contract records stake; wrong token rejected/refunded.
FR-05
Close by cutoff time and refuse late positions.
Boundary timestamp unit test.
FR-06
Resolve only through authorized resolver with evidence hash and
formula version.
Non-resolver call rejected; result idempotent.
FR-07
Claim payout exactly once; recover safely from failed transfer.
Repeated claim cannot drain escrow.
FR-08
Void unresolved invalid market and let users reclaim original
stake.
All eligible accounts recover amount once.
#### Research, proof, funding and privacy
ID
REQUIREMENT
ACCEPTANCE TEST
FR-09
Generate evidence-linked NEAR AI trend brief; show source links
and generation time.
Brief cannot write settlement state.
FR-10
Show all market observations, raw source URLs, canonical
evidence JSON and digest.
Local resolver reproduces committed hash.
FR-11
Execute Tidepool testnet quote -> deposit -> status funding
demonstration.
One explorer-verifiable success; no real funds.
FR-12
Optional official 1Click mainnet dry quote, clearly labeled
non-executable from testnet UI.
No bridge from test asset into mainnet quote.
FR-13
Share route-specific market URL with static Open Graph preview.
Link opens same market on mobile.
FR-14
Owner-only research watchlists and notes.
Different user cannot read another owner's notes.
FR-15
Commit-reveal market configuration as optional P2 mode.
Public chain hides choice until valid reveal; misses handled.
FR-16
Report current privacy boundary and link to a clear privacy
disclosure.
No blanket claim of anonymity.


## Source page 6
#### Non-functional requirements
AREA
REQUIREMENT
Security
Use server-only keys, validate all chain inputs, avoid key custody, make payouts
non-reentrant/idempotent.
Reliability
Bounded retries and explicit terminal statuses for data, swaps, claims and oracle jobs.
Accessibility
Keyboard-friendly navigation, form labels, visible errors, contrast and screenreader descriptions.
Performance
Cache public reads; render market and chart content before optional AI brief.
Data integrity
Versioned formula, canonical JSON serialization, source attribution and tamper-evident hash.
Observability
Trace ID per swap/market job, redacted logs, error events and demo evidence log.
Maintainability
Strict TypeScript, Rust unit tests, separated domain logic and fixtures.
### 4 The technical architecture
#### Consumer web application
Discover  |  Research  |  Fund  |  Trade  |  Claim
Research + evidence
Wikimedia, NEAR AI, YouTube context
Wallet + Intents adapter
NEAR wallet, Tidepool testnet
NEAR testnet market contract
Positions  |  Collateral  |  Resolution  |  Claims  |  Refunds
Boundary A - frontend: Next.js/React/Tailwind renders public market state, private account data and wallet
interactions. It cannot resolve markets, hold resolver keys or store raw NEAR AI secrets.
Boundary B - application API: Serves curated market metadata, cached public data, AI briefs, oracle evidence and
user-owned research. It verifies wallet-signed login messages for private features. It never becomes the canonical
ledger of stakes or payouts.
Boundary C - data/oracle worker: Retrieves pageviews, persists snapshots and hashes, evaluates deterministic
formulas, and queues authorized resolution after data freshness checks. A market is not automatically resolved by the
language model.


## Source page 7
Boundary D - chain contract: Holds accounting truth for positions, escrow, outcome, claims/refunds and authorization.
Only the configured settlement token is accepted.
Boundary E - Intents adapter: A separate provider integration demonstrates Tidepool testnet swap, resulting wallet
receipt, and optional read-only official mainnet quote. Provider statuses are not claims inside our market contract.
Suggested repository layout
notch/
  apps/web/                  # Next.js app, wallet + market UX
  packages/domain/           # market rules, canonical evidence
  packages/near/             # typed contract + FT client
  packages/intents/          # Tidepool + official quote adapter
  services/oracle/           # Wikimedia snapshots + resolution
  contracts/market/          # Rust NEAR SDK market contract
  tests/e2e/                 # wallet and claim flows
  docs/                     # ADRs, oracle, security, judge guide
  scripts/                  # seed market, fixtures, evidence
  .env.example               # names only, no secrets
#### Application database entities
ENTITY
KEY FIELDS / PURPOSE
topics
id, slug, sourceKey, articleTitle, displayName, category, createdAt.
markets
id, chainId, contractMarketId, mode, question, configVersion, status, timestamps.
source_snapshots
marketId, source, rawPayloadRef, observedAt, window, hash, fetchState.
resolution_evidence
marketId, canonicalJson, digest, computedOutcome, submittedTx, resolverVersion.
ai_briefs
topicId, sourceSetHash, model, generatedAt, brief, citations, limitations.
user_watchlists / notes
walletId, encrypted/or access-controlled content, createdAt, updatedAt.
intents_runs
runId, provider, quoteId, status, fundingTx, receiverTx, errors (redacted).
#### DATA AUTHORITY RULE
Database mirrors public chain state for convenience; it never determines payouts. Wallet balance and market settlement are always
read from NEAR contract/token state.


## Source page 8
### 5 Onchain market design and financial logic
#### Suggested contract state
OBJECT
FIELDS
Config
owner / marketOperator; resolver; allowedNep141Token; feeBps = 0; paused flag.
Market
id; mode; choices; source descriptor; frozen rule hash; openAt; closeAt; resolveAfter; status; totals[2]; escrowTotal;
evidenceHash; result.
Position
marketId; accountId; side; depositAmount; claimedAmount; claimState; optional sealed commitment.
Claim ledger
claimable amount per account; pending transfer info; completed / failed flags.
#### Pooled binary payout formula
Let a market contain test-token stake totals T_A and T_B, with T = T_A + T_B. For an account whose stake on the
winning side is s, the gross payout is:
PAYOUT ARITHMETIC
payout = floor(s × T / T_winning), where T_winning is the total stake on the winning side. All amounts are unsigned integer base
units (for USDC, verify live token decimals). Remainders from flooring stay in a documented reserve to be handled by a
precommitted dust rule. Fee = 0 in MVP.
Conservation test: the total amount transferred to winning positions must never exceed T. The sum of outstanding
claims plus pending transfers plus paid claims plus any documented dust must equal the contract-accounted escrow
for each market.


## Source page 9
#### Critical edge cases
SCENARIO
PROPOSED MVP RULE
No positions
Market can expire empty; no payout actions.
Only one side funded and that side wins
All winning stakers reclaim their own amount; no manufactured profit.
Winning side has zero stake
Void and permit all stakers to reclaim, instead of trapping funds.
Tie in battle
Void, unless precommitted tie option exists; MVP uses void.
No reliable data / source removed
Void after configured deadline and audit log.
User claims twice
Second claim rejected or returns zero without transferring again.
Failed outbound FT transfer
Reconcile promise status and restore eligibility safely.
Wrong token/late ft_transfer_call
Return unused amount through NEP-141 receiver path.
Contract paused
No new markets/entries; existing claims and refunds remain possible where safe.
#### NEP-141 deposit and withdrawal sequence
01 Wallet calls test token `ft_transfer_call(receiver_id = marketContract, amount, msg = position params)`.
02 Receiver verifies predecessor token ID, message schema, market open state, allowed stake and chosen side.
03 Receiver records stake and returns the appropriate unused amount under NEP-141 semantics.
04 Resolver later records a deterministic result and evidence digest.
05 Claim handler computes integer payout, marks transfer pending and calls token `ft_transfer`.
06 Callback finalizes successful claim or safely restores unpaid claim on failure.
The exact Rust implementation must follow current NEAR SDK patterns and NEP-141 receiver semantics, including
cross-contract callback access control. [S6]
#### Market lifecycle / state machine
DRAFT -> OPEN -> CLOSED -> AWAITING_DATA
                        |               |
                        |         RESOLVED -> CLAIMABLE -> FINALIZED
                        +-----> VOID -> REFUNDABLE -> FINALIZED
Every state transition is authorization-checked and idempotent. Time uses onchain block timestamps, with the unit
documented. Manual operator override can only VOID, never invent a different winner after evidence is frozen.


## Source page 10
### 6 Oracle design, evidence and market timing
#### Source and market configuration
Start with Wikimedia Analytics API daily pageviews for a specifically named article on a specifically named language
wiki, using a server-side identified User-Agent, response caching and rate-limit compliance. Its data is CC0; the display
must attribute the source and observation window. [S7, S8, S14, S16]
CONFIG FIELD
EXAMPLE VALUE / RULE
sourceId
wikimedia-pageviews-v1
project
en.wikipedia.org
articleTitle
A frozen canonical article title, validated on setup
access / agent
all-access / user (verify available API field; exclude spiders where appropriate)
baselineWindow
An already-published full reporting day or selected historical reference
targetWindow
A subsequent full reporting day; not an unverified future partial count
metricFormula
(targetViews - baselineViews) / max(baselineViews, minBaseline) * 100
minimumBaseline
Configurable non-zero threshold to avoid microscopic denominator artifacts
settlementClock
Resolve only after target day data is available; publication can lag
#### Trend Trading rule
Outcome UP if target daily pageviews growth is at least the precommitted threshold (example 15.00%). Otherwise
DOWN. Snapshot includes source identifiers, response body digest, baseline and target counts, formula version,
threshold, observation windows, fetched timestamps, resolver code version and final outcome.
#### Trend Battles rule
For topics A and B measured over the same date windows, calculate separate growth percentages and compare. If
absolute difference is below the predeclared tie tolerance, void; otherwise the higher-growth topic wins. Baseline
minimum and article identity checks must pass for both sides.


## Source page 11
#### Evidence receipt design
```json
  "schemaVersion": "1", "marketId": "...",
  "source": "wikimedia-pageviews-v1",
  "query": {"project":"en.wikipedia.org", "article":"..."},
  "baseline": {"date":"...", "views":"..."},
  "target": {"date":"...", "views":"..."},
  "formulaVersion":"growth-v1", "thresholdBps":1500,
  "outcome":"UP", "fetchedAt":"...",
  "rawResponseHash":"sha256:...", "resultHash":"sha256:..."
}
```
Generate the evidence hash from a canonical UTF-8 JSON serializer, using a versioned schema and sorted keys. Store
original fetched response or archival reference outside the chain, then commit the digest and outcome onchain. Verify
a third-party reproduction can produce the same digest. A hash is tamper evidence, not proof that views are organic.
Time reality and demo fallback
#### CRUCIAL SCHEDULING REALITY
Daily Wikimedia data usually is not available in real time. A market opened on Nov 13 for Nov 14 daily views may not resolve
before the Nov 14 submission cutoff. Therefore demo two distinct modes: (1) genuine data-backed markets that resolve when the
data is published; and (2) clearly labeled replay markets using previously published daily observations, with fully real onchain
collateral and settlement. A seeded replay is not a live forecast.
#### Source-health gates
- Reject unavailable pages, unresolved redirects, ambiguous article mapping and timestamp mismatch.
- Use a frozen, deterministic version of the source query, transform and formula.
- Apply minimum baseline / missing data / reporting delay rules uniformly.
- Keep Youtube and Google signals in a separate context service, not the oracle calculation.
- Store input/output hashes and machine-readable reasons for voiding.
### 7 NEAR Intents funding: technical integration


## Source page 12
#### Two distinct integrations
PROVIDER
PURPOSE
HARD BOUNDARY
Tidepool community sandbox
Testnet quote -> deposit address -> testnet deposit ->
maker settlement -> receiver wallet -> status.
Not official; single trusted maker; custodial
deposit address keys; no real funds; no
confidentiality.
Official NEAR Intents 1Click
Mainnet read-only token list / dry quote to
demonstrate forward compatibility.
No testnet; no actual mainnet deposit or
trade in this MVP.
#### Funding workflow (must be verifiable)
01 Detect network; require a NEAR testnet wallet for trading.
02 Read supported Tidepool assets from live `/v0/tokens` rather than hard-coding decimals or IDs.
03 Request a quote (dry first, then executable), capture quote expiry and recipient wallet ID.
04 User deposits only test tokens to the provided testnet address; follow provider memo rules where applicable.
05 Poll `/v0/status` with bounded backoff and inspect terminal SUCCESS or refund/failure reason.
06 Wait for the destination NEP-141 test-token balance on the user wallet.
07 Separately use `ft_transfer_call` from that wallet into the market contract. Do not call a funding swap a market
position.
08 Show swap proof and market entry proof as two different transactions.
#### Trust disclosures
Tidepool documentation says it operates a single maker and derives deposit-address keys. Testnet assets have no
value. Swaps settle publicly on testnet; confidential intents are not supported. The official 1Click service is mainnet
only. Client code should isolate providers and display distinct environment labels. [S3-S5]
#### Integration states
STATE
UI TREATMENT / ACTION
QUOTE_READY
Show expected receipt, fee, expiry and test-only warning.
PENDING_DEPOSIT
Show deposit instructions and exact address/memo.
INCOMPLETE_DEPOSIT
Explain shortfall; only permit safe additional testnet deposit within deadline.
PROCESSING
Poll with exponential backoff and timeout cap.
SUCCESS
Confirm destination token balance, then offer Enter Market.
FAILED / EXPIRED /
REFUNDED
Stop flow, show refund details or retry steps; never mark funded.


## Source page 13
### 8 NEAR AI and free-first external APIs
#### AI research contract
NEAR AI Cloud is OpenAI-compatible and currently pay-as-you-go, not guaranteed free. Use model catalog validation
and a small explicit spend cap. AI input includes only public and permitted source materials; output must cite links and
avoid providing personalized financial advice. [S12-S13]
INPUT
OUTPUT
GUARDRAIL
Topic, sourced excerpts,
timestamps, pageviews
Brief explanation, trend drivers, what data does
not establish.
Only provided sources; source URL links; no
fabricated claims.
Frozen market config
Plain-English resolution explanation.
Do not alter target, threshold, dates or result.
Relevant existing markets
Related research suggestions.
Do not create an outcome or execute a position.
#### Credential and quota matrix
SERVICE
KEY / ACCESS
COST / POLICY / HANDLING
Wikimedia
No API key; identified User-Agent
with contact.
CC0; cache; obey 429 and rate limits.
Hacker News
Public API; no key for public
endpoints.
Optional non-oracle research; verify data stability.
YouTube Data API
Google Cloud API key, restricted to
API and backend.
Default 100 search calls/day and 10,000 other units/day; policies
constrain derived/aggregated metrics.
Google Trends
Public contextual views where
permitted.
Official API availability restricted; no scraping to guarantee outcomes.
NEAR AI Cloud
Server-side NEAR_AI_KEY.
Per-token charges; tiny spend cap, caching, graceful fallback.
Tidepool
Standard swap endpoints do not
require an API key.
No real assets; no confidential settlement.
Official 1Click
Provider-specific auth may improve
quote fee tier.
Mainnet quote only; no testnet execute.
App database
DATABASE_URL, managed secret.
Use available free tier where eligible; ensure backups and access
control.


## Source page 14
#### Server environment template
```dotenv
NEAR_NETWORK=testnet
NEAR_RPC_URL=https://rpc.testnet.near.org
MARKET_CONTRACT_ID=
COLLATERAL_TOKEN_ID=
TIDEPOOL_BASE_URL=https://www.usetidepool.tech
OFFICIAL_1CLICK_BASE_URL=https://1click.chaindefuser.com
NEAR_AI_BASE_URL=https://cloud-api.near.ai/v1
NEAR_AI_KEY=
YOUTUBE_API_KEY=                # optional research only
WIKIMEDIA_CONTACT=
DATABASE_URL=
RESOLVER_KEY_REFERENCE=          # server-side secret manager, not raw in repo
```
Keep a committed `.env.example` with placeholders only. Never expose provider or signing keys through
browser-visible env variables. Use delegated access, signed login challenges for private research, and an operator key
with minimal authority. No secrets in repository history or screenshots.
### 9 Privacy model and phased rollout
#### Privacy threat model
ADVERSARY / OBSERVER
WHAT THEY COULD SEE
DEFENSE / LIMIT
Public blockchain observer
Contract addresses, deposits,
timestamps and public positions.
No claim of invisible stake/account in P0.
Other user in application
Public market data; might guess
strategies from history.
User notes are access-controlled and offchain.
App backend operator
Stored private notes unless genuinely
client-encrypted.
Minimize data, strict access, optional client encryption later.
Sealed-market observer
Commit hash and deposit amount but
not side.
Random salt, domain-separated hash, reveal only after close.
Sandbox operator
Tidepool maker and deposit-address
custody in testnet.
Never send real funds; disclose third-party trust.
#### P1: owner-only research
Wallet signature login with domain, nonce, chain and expiry; server verifies proof, issues scoped session, and enforces
ownership on watchlist and notes queries. Keep account identifiers pseudonymous but do not call server-side storage
fully private from operators. Content security policy and transport encryption are required.


## Source page 15
#### P2: commit-reveal hidden outcomes
01 For a sealed market, every entrant must use commitment mode; do not mix public positions and sealed ones
without a formally reviewed accounting design.
02 Commit a hash that includes chain ID, contract ID, market ID, account, choice, stake, nonce and high-entropy
secret salt.
03 Contract records stake and commitment before close; the selected side is not submitted in plaintext.
04 After close, a bounded reveal phase lets user submit the choice, nonce and salt.
05 Contract checks the domain-separated hash, assigns stakes to revealed outcome pools and then permits
resolution.
06 Non-reveal stakes cannot receive a winning payout (otherwise losers could free-option by withholding reveals).
State this before commitment; voids refund all original stakes.
07 Offer local encrypted secret export and repeated reveal reminders. Losing a secret can mean losing the stake
under the agreed rules.
Choice secrecy is meaningful only if commitment entropy is sufficient and client code does not leak the side through
telemetry or requests. The technical proof is that a block explorer cannot infer the choice before reveal from the
commitment alone. Amount and wallet remain public.
#### V2: selective disclosure and confidential funding
Verified performance-sharing requires selective attestations or scoped permissioned records; hiding an element in the
UI is not privacy. Official Confidential Intents remains a separate mainnet capability. A future mainnet rollout must test
its actual visibility guarantees and limits; the Tidepool sandbox cannot demonstrate it. [S3-S5]
### 10 API endpoints and contract interface sketch


## Source page 16
#### Application API (illustrative)
METHOD / ROUTE
PURPOSE
ACCESS
GET /api/topics
Curated topics, source references and research metadata.
Public
GET /api/markets
Market index, chain-derived status, source metadata.
Public
GET /api/markets/:id/evidence
Immutable config, snapshots, calculations and digest.
Public
GET /api/trends/:slug/brief
Cached NEAR AI explanation and source links.
Public
POST /api/quotes/tidepool
Server validation / proxy for testnet quote.
Rate-limited
GET /api/swaps/:runId
Normalized provider swap status, redacted fields.
Owner/session
POST /api/auth/challenge
Wallet-signature nonce creation.
Public /
rate-limited
POST /api/auth/verify
Verify signature and create scoped session.
Public
GET/POST /api/research
Owner-only watchlists and notes.
Authenticated
POST /internal/oracle/resolve
Produce signed evidence/resolution job.
Operator only
#### Contract methods (names to be finalized in repo)
INTERFACE
INPUT / BEHAVIOR
create_market(config)
Authorized operator; immutable mode, dates, source hash and policy.
ft_on_transfer(sender, amount, msg)
Validated stake entry via approved token.
close_market(market_id)
Permissionless time-guarded transition, idempotent.
resolve_market(market_id, outcome,
evidence_hash)
Resolver-authenticated; commits final result.
void_market(market_id, reason_hash)
Restricted conditions and reason; enables refunds.
claim(market_id)
Eligible user receives calculated payout, safe callback.
claim_refund(market_id)
Void participant receives original contribution once.
get_market / get_position / get_claimable
Public view methods for client and auditors.


## Source page 17
### 11 Tests, evidence and launch gates
#### Contract test matrix
TEST CLASS
REQUIRED CASES
Access control
Wrong market operator; wrong resolver; repeated initialize; paused mode.
Deposits
Valid FT; wrong token; malformed message; late market; zero stake; excessive deposit.
Lifecycle
Open -> close -> resolve; invalid transitions; duplicated resolve; clock boundaries.
Payout accounting
Both sides funded; one side funded; zero winners; dust; large integer arithmetic.
Claim safety
Double claim; failed promise; retry; no funds siphoned.
Void/refund
Missing source; tie; expired/unresolved; repeated refund.
Oracle
Hash determinism, changed source data detection, rounding and threshold equality.
Sealed P2
Invalid salt; wrong market; replay; pre-reveal access; non-reveal policy.
#### Integration tests
- Fresh testnet wallet connects, faucets, receives collateral and makes FT deposit.
- Tidepool quote/deposit/status sequence ends in real test-token receipt, with observed hashes.
- One market of each type resolves; claim transaction confirmed by explorer.
- Wikimedia outage leads to AWAITING_DATA or VOID, not guessed payout.
- NEAR AI failure returns "brief unavailable" without breaking trading.
- YouTube API key missing returns a disabled context feature, not a server crash.
- Private research attempts using different wallet sessions fail authorization.
- Mobile wallet UX and deep links preserve market ID.


## Source page 18
#### Evidence ledger required for judges
ARTIFACT
EXAMPLE EVIDENCE
Contract deployment
Account ID, deploy transaction, wasm hash.
FT deposit
Token contract, wallet, amount, transaction hash.
Two market entries
Mode, market ID, wallet, entry transaction hashes.
Resolutions
Evidence JSON hashes, resolver job logs, onchain result transaction.
Claims / refunds
Proof of balance transfer, claim status and explorer links.
Intents sandbox
Quote + status metadata, Tidepool settlement and wallet receipt hash.
AI generation
Request metadata, source list, cached brief and model ID (no key).
#### Quality gate definitions
GO / NO-GO
GO only when both modes can enter and claim, chain reconciliation passes, at least one Intents-compatible swap is verifiable, and
README steps work on a fresh environment. NO-GO for hidden positions if reveal economics, secret loss and callback behavior
are not fully tested.
### 12 Four-day delivery plan and critical path
All times below are in West Africa Time (WAT, UTC+1). The hackathon closes 15 November 2026 at 00:59 WAT (14
Nov 23:59 UTC). Aim to submit with buffer. [S1, S15]
WINDOW
SLICE / DEPENDENCIES
EXIT ARTIFACT
11 Nov - Phase 0
Finalize payout and oracle policy. Bootstrap repo. Test wallet, USDC
token, Tidepool quote and Wikimedia availability.
Signed ADRs; running Next.js shell; verified
token/provider config; first source
snapshot.
12 Nov - Phase 1
Rust contract, NEP-141 deposit, both modes, close, resolve, void,
claim callbacks; unit tests and deployment.
Two real NEAR testnet markets;
documented deployment and transactions.
13 Nov AM - Phase 2
Oracle resolver, evidence digest and two deterministic replay markets;
chain-to-UI wiring.
Resolved and claimed market of each type
with reproducible receipts.
13 Nov PM - Phase 3
Tidepool live testnet deposit + status, NEAR AI briefs, wallet/funding
UX, share pages and optional private notes.
Full new-user flow; credible Intents
evidence; deployed app.
14 Nov - Phase 4
Security regression, mobile, observability, README, video, X demo,
submission. P2 sealed only if P0/P1 stable.
Public repo, judge guide, demo proof,
submitted form with buffer.


## Source page 19
#### Agent-friendly work slices
SLICE
BUILD THE SMALLEST PROOF
DO NOT DO
S0 - environment
Wallet, provider health and source data spike.
No broad architecture refactor.
S1 - market core
One contract, a deposit, a claim.
No UI polish or features unrelated to proof.
S2 - second mode
Use same accounting with different resolver config.
No duplicate market engine.
S3 - evidence
Freeze data, compute outcome, record digest.
No AI-controlled settlement.
S4 - Intents
Live Tidepool testnet funds -> wallet, distinct from market deposit.
No real tokens or fake mainnet swap.
S5 - consumer
Discover, market, portfolio, claim and share.
No premature advanced order book.
S6 - privacy stretch
Owner-only notes; sealed commitments only if safe.
No "fully private" claim.
#### Critical path and contingency
The dependency chain is token validation -> ft_transfer_call -> market state -> resolution evidence -> payout -> judge
reproduction. Any delay here outranks visuals. A second dependency is Tidepool quote -> deposit -> receipt. If that
fails, record the exact error and do not fabricate Intents execution; retain a real official read-only quote and a
transparent status report.


## Source page 20
### 13 Security, operations and risk register
RISK
PROBABLE IMPACT
MITIGATION / OWNER
Oracle manipulated or stale
Wrong settlements / user trust collapse.
Freeze sources; eligibility gates; snapshots, hashes and VOID.
Oracle owner.
Provider or data outage
Cannot complete demo.
Historical replay labeled clearly; bounded retries; source fallback
for research only. Backend owner.
YouTube policy violation
API suspension or compliance issue.
Never use unapproved derived metrics in payout oracle; comply
with terms. Product owner.
Payout contract bug
Locked or double-spent tokens.
Integer tests, callbacks, no fees/leverage, tiny test stakes. Contract
owner.
Non-reveal in sealed market
Position loss and reputation damage.
Clear policy, secret backup and reminders; P2 gate. Security
owner.
Tidepool trust/compatibility
Funding blocked or misunderstood.
Test tokens only, disclosure, adapter and status proof. Integrations
owner.
NEAR AI quota/cost
Unexpected billing or broken pages.
Small cap, caching, optional brief fallback. Infra owner.
Scope creep
Missed submission.
P0 hard freeze; P2 and enhancements deferred. Product owner.
Regulatory classification
Mainnet service may be prohibited.
Testnet only; jurisdictional counsel before real-money launch.
Founder.
#### Operational observability
- Use structured logs including marketId, swapId, chainId, requestId and state transition, with wallet data minimized.
- Emit event/error counters for source failures, pending payouts, failed FT transfers and Intents stalls.
- Preserve a downloadable, redacted evidence bundle with transaction hashes and deterministic fixtures.
- Use one-click pause of new market creation/entries for emergencies; keep already-earned claims accessible unless
safety dictates otherwise.
- Do not put signing keys, API keys or private research content in third-party analytics.
### 14 README, demo and submission packaging
#### Public README must answer
01 What is the product and which NEAR hackathon tracks does it fit?
02 What is implemented now versus planned later, especially privacy and continuous trading?
03 How to install, configure safe placeholder secrets, test and start it?
04 What are contract IDs and test token IDs? Where are explorer links?


## Source page 21
05 How can an AI judge independently reproduce an entry, resolution and payout?
06 What data is live, what is an archived replay, and how is evidence hashed?
07 What does Tidepool do, and why is it not official/mainnet NEAR Intents?
08 What are known limitations, risk disclosures and licenses?
#### Demo target: 2.5 to 3.5 minutes
BEAT
SHOW
00:00-00:20
Problem + product promise: attention markets with verifiable outcomes.
00:20-00:45
Trend page, source window and brief with cited research.
00:45-01:15
Tidepool testnet funding status and NEAR token receipt.
01:15-02:00
Enter Trend Trading and Trend Battle positions on NEAR.
02:00-02:40
Deterministic resolve, evidence hash and winner claims.
02:40-03:10
Explorer proof, privacy roadmap disclosures and shareable market.
#### Submission final checklist
- Public GitHub repository with license and no secrets in history.
- Live deployed app or fully reproducible local demo, plus deterministic fixtures.
- Public X demo post tagging @NEARProtocol and #NEARHackathon.
- Project submission form with repository URL, X post URL and a mainnet NEAR account for prize payment.
- Both applicable tracks selected and original work disclosed.
- README contains exact "do X, see Y" steps for AI judges.
- Submit before 14 November 23:59 UTC; verify submission confirmation. [S1, S15]


## Source page 22
### 15 Post-hackathon version plan
VERSION
PLANNED PRODUCT EXPANSION
GATE
V1 beta
Real-time market reliability, stronger oracle checks, better UX and
testnet activity.
Repeat users and verified metrics.
V2 trading
Secondary selling / early exits; AMM or order-book design;
cross-platform indicators.
Formal liquidity, accounting and oracle
model.
V2 privacy
Selective verified performance, proper private storage and
confidentiality evaluation.
Threat model, privacy tests, production
security review.
V2 mainnet
Official Confidential Intents and regulated real-money trading only if
permitted.
External security audit, legal review and
funding risk controls.
V3 platform
Community-owned markets, data/API products and creator economics.
Proven market integrity and
abuse-resistant data.
#### LAST ENGINEERING PRINCIPLE
Build what the judge can verify, not what a pitch deck can promise. Every claimed NEAR integration should yield a working action,
status, test, receipt or clearly documented limitation.


## Source page 23
## Sources
Reviewed 11 November 2026. References substantiate external facts; proposed product behavior and architecture are design
decisions, not already-shipped capabilities. Links should be rechecked before submission.
[S1] NEAR Hackathon official website and submission rules
https://nearhackathon.com/
[S2] NEAR Hackathon guide and starter resources
https://github.com/nearai/near-hackathon-prompt-examples
[S3] Official NEAR Intents 1Click quickstart (mainnet only)
https://docs.agentsonintents.com/integration/distribution-channels/1click-api/quickstart/introduction
[S4] Tidepool community sandbox documentation and trust model
https://www.usetidepool.tech/docs
[S5] Tidepool compatibility / quickstart
https://www.usetidepool.tech/docs/quickstart
[S6] NEAR fungible-token specification, NEP-141
https://github.com/near/NEPs/blob/master/neps/nep-0141.md
[S7] Wikimedia Analytics API documentation
https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/getting-started.html
[S8] Wikimedia Analytics API access and licensing policy
https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html
[S9] YouTube Data API quotas
https://developers.google.com/youtube/data/determine_quota_cost
[S10] YouTube Developer Policies (including derived metrics)
https://developers.google.com/youtube/terms/developer-policies
[S11] YouTube policy guide for derived metrics and aggregation
https://developers.google.com/youtube/terms/developer-policies-guide
[S12] NEAR AI Cloud and pricing
https://near.ai/pricing
[S13] NEAR AI Cloud API overview
https://near.ai/
[S14] Wikimedia pageviews endpoint examples
https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/examples/page-metrics.html
[S15] Hackathon submission checklist
https://github.com/nearai/near-hackathon-prompt-examples/blob/main/SUBMITTING.md
[S16] Wikimedia API rate limits
https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits
