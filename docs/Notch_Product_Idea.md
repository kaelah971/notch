---
title: "Notch | Full product idea"
brand: "Notch"
descriptor: "Evidence-led attention markets"
status: "Planning / not yet deployed"
source_basis: "Supplied full product idea source, reconciled with the supplied PRD and official NEAR Hackathon sources"
date: "11 November 2026"
---

# Notch | Full product idea

> **Descriptor:** Evidence-led attention markets  
> **Primary line:** Where attention turns into evidence.  
> **Build boundary:** NEAR testnet first  
> **Status:** Planning / not yet deployed

## Claim status

- **Shipped:** No implementation evidence was supplied for this engagement.
- **Target:** Capabilities specified for the hackathon build.
- **Roadmap:** Capabilities intentionally deferred beyond the hackathon core.
- **Hypothesis:** Positioning and differentiation assumptions that still need testing.

This is the editable product-idea document for Notch. It preserves the supplied product intent while replacing the provisional source identity with the locked brand. The original source PDF remains unchanged.

## Executive concept

### An internet attention market, built on NEAR

Notch is a consumer-first market platform where people discover emerging topics, understand the evidence behind their momentum and take fully collateralized testnet positions on measurable future attention. It combines two market experiences, Trend Trading and Trend Battles, on a shared NEAR smart-contract settlement engine.

### One-sentence pitch

> Take a bounded position on the direction of attention or the winner of a trend contest, with transparent measurement, explainable research, NEAR-powered settlement and an honest privacy roadmap.

## What Notch delivers

### Two market modes

- **Trend Trading:** UP or DOWN against a predefined target.
- **Trend Battles:** topic A versus topic B under a matched growth rule.

### Verified attention

The market precommits its source, observation window, formula and final evidence receipt. A hash connects the evidence to the onchain result when the target settlement flow ships.

### NEAR-centered finance

The target build uses NEAR testnet wallets, NEP-141 test-token collateral, positions, payouts and a real Intents-compatible funding demonstration.

### NEAR AI trend intelligence

NEAR AI may produce source-linked explanations, market context and known limitations. It does not control payouts, resolve markets or execute a position.

### Privacy by design

Private research comes first. Commit-reveal positions, selective disclosure and confidential funding remain separate phases with separate guarantees.

### Free-first data

Wikimedia is the primary oracle candidate. YouTube and Google may provide permitted research context. The design uses free testnet assets and limited AI usage where available, subject to current policy and quota checks.

## Why this product now

The internet produces waves of attention, but people have few transparent tools for discovering those waves, understanding them and taking bounded positions on measurable outcomes. Existing attention products, prediction markets and social tokens show conceptual interest, but they also expose hard problems:

- engagement can be manipulated;
- resolution can be opaque;
- derivatives can be confusing;
- chain funding can be fragmented;
- AI summaries can blur observation and interpretation.

The product idea draws inspiration from mechanisms seen in projects such as Trendr, Eros Markets, Amplifi, Hunch and Copycat. Those references are inspiration, not a claim that comparable products are absent from NEAR or elsewhere. Notch deliberately avoids GPU-finance ideas.

## 1. The problem and user opportunity

| Persona | Problem | Product job |
|---|---|---|
| Trend explorer | Sees a topic spreading but cannot quantify or contextualize it. | Discover a topic, compare credible signals and read an AI brief. |
| Consumer market participant | Wants simple stakes and clear settlement instead of leverage. | Choose a side, view exposure and claim a verified testnet payout. |
| Research-minded trader | Does not want every watchlist or hypothesis to be public. | Maintain a private research workspace and control what is shared. |
| Community organizer | Wants a shareable, objective question that encourages participation. | Share a battle card and send users to its specific market. |
| NEAR ecosystem user | Wants meaningful cross-chain infrastructure in action. | Use a NEAR wallet, inspect contract state and see Intents-style funding. |

## Promise and boundaries

- **Promise:** A market question that a user can understand before committing any test tokens.
- **Promise:** Every outcome links to a source, fixed rule, evidence snapshot and blockchain receipt when the target path ships.
- **Boundary:** The hackathon build uses valueless testnet tokens, not live customer funds.
- **Boundary:** Private watchlists are not private chain transactions. Privacy claims remain scoped.
- **Boundary:** The initial market is a time-limited pooled binary market, not a leveraged perpetual exchange.

## 2. Two market experiences, one engine

### Mode A: Trend Trading

Users open a topic and choose whether its attention will reach a specific, measurable threshold within a fixed observation window.

Illustrative question:

> Will daily article views for Topic X grow by at least 15% against its frozen baseline?

Users enter UP or DOWN with test USDC. After the relevant data is available, the market resolves and eligible winners can claim.

#### Illustrative market

- **Market:** AI Agents attention increases by at least 15% by the end of a defined Wikimedia reporting day.
- **UP:** The published calculation crosses the threshold.
- **DOWN:** The calculation does not cross the threshold.
- **Frozen before entry:** metric, source, timestamp and handling of missing data.

### Mode B: Trend Battles

Users choose which of two comparable topics will have higher normalized growth over the same observation period.

Illustrative question:

> AI Agents versus Gaming: which topic grows faster?

The battle uses matched time windows, comparable Wikimedia pages or documented topic baskets and a predetermined tie rule.

The early version uses pari-mutuel pooled settlement. Stakes accumulate on each side and winners share the combined pool proportionally. Notch does not promise fixed odds, guaranteed prices or early exits. An advanced market maker or continuous attention index is a later iteration.

## What a user sees

1. Explore markets by topic, category, time remaining and status.
2. Open a market page with a trend chart, precise resolution rule, source link, risks and a research brief.
3. Connect a NEAR testnet wallet and obtain test USDC through a faucet or an explicitly labeled Intents-compatible testnet swap.
4. Choose an outcome, enter a test-token amount and approve a real contract transaction.
5. Track the position in Portfolio while the market awaits its data.
6. Inspect the evidence receipt after resolution, then claim an onchain payout or refund.
7. Share the market URL, not a generic homepage link.

## 3. Trend intelligence: explain the attention

Each topic has a research page, not only a price chart. NEAR AI can summarize public context from a fixed collection of cited sources and explain what the attention metric measures. The user must be able to separate observed data from AI interpretation.

| Component | Content |
|---|---|
| Attention chart | Raw observations, reporting period, source label, refresh time and gaps. |
| Notch Brief | Plain-language topic overview, plausible drivers, source links and explicit uncertainty. |
| Related markets | Trend Trading questions and relevant Trend Battles, each with its own rule. |
| Transparency panel | Frozen market definition, oracle status, settlement account and receipt links. |
| Share card | Question, two options or target, closing time, source badge and canonical market link. |

## Free-first data hierarchy

| Source | Role | Restrictions and cautions |
|---|---|---|
| Wikimedia Pageviews | Primary MVP market-resolution candidate with daily windows. | CC0 data and identified User-Agent. Publication can lag. Use source-specific topics. |
| Hacker News API | Optional technology-trend discovery and research. | Check bot traffic and metric stability. Not automatically a settlement oracle. |
| YouTube Data API v3 | Video metadata, public statistics and permitted discovery context. | Free default quotas, strict aggregation and derived-metric restrictions. Not the default payout oracle. |
| Google Trends | Supplemental public context if access and terms permit. | Official API access is restricted. Do not depend on unauthorized scraping. |
| NEAR AI Cloud | Evidence-linked written summaries and optional confidential inference. | Usage-based pricing. Verify credits, cap spend and provide a fallback. |

### Honest limitation

Wikimedia daily pageviews are not instant social-media attention. The MVP should be described as a transparent internet-interest market with its measurement source named. Faster multi-platform attention indexes remain research-stage.

## 4. Privacy as a product layer

| Capability | User value | Build status |
|---|---|---|
| Private saved research | Watchlists, notes and hypotheses are available only to the owner. | Target P1. Secure authenticated storage, not onchain. |
| Hidden-until-reveal positions | Selected side is concealed during a commit phase. | Roadmap P2. Requires a commit-reveal contract and missed-reveal policy. |
| Selective performance disclosure | Show a verified performance summary without exposing every tactic. | Roadmap V2. Requires an evidence model and genuine access control. |
| Confidential Intents funding | Reduce disclosure of eligible cross-chain swap details. | Roadmap V2 / mainnet. Use only official confidential infrastructure if supported. |

The testnet market contract remains public. In a commit-reveal design, the commitment hash can hide the choice, but it does not necessarily hide the wallet, stake amount or time of entry. Tidepool does not implement confidential Intents. Notch must never call the MVP an anonymous exchange.

## 5. Why NEAR is central

The chain is part of the user action, not a logo in the footer.

```text
Consumer web application
Discover  |  Research  |  Fund  |  Trade  |  Claim

Research + evidence
Wikimedia, NEAR AI, YouTube context

Wallet + Intents adapter
NEAR wallet, Tidepool testnet

NEAR testnet market contract
Positions  |  Collateral  |  Resolution  |  Claims  |  Refunds
```

| NEAR component | Why the user cares |
|---|---|
| NEAR Rust smart contract | Public market state, escrowed test collateral, resolution, payouts and refunds can be inspected. |
| NEP-141 fungible tokens | A test-USDC-style collateral asset enters through a defined transfer protocol. |
| NEAR Intents-compatible sandbox | A development-path quote, deposit, settlement and status flow can be shown through Tidepool on testnet. |
| Official 1Click API | A separate read-only mainnet quote can demonstrate forward compatibility. It is not a live testnet swap. |
| NEAR AI | Trend briefs can be source-linked and easier to understand. NEAR AI is not the oracle or trade executor. |
| NEAR explorer and receipts | A judge or user can verify the transaction and market state independently. |

### Funding boundary

Official NEAR Intents 1Click does not provide a testnet. Tidepool is an unaffiliated community-operated 1Click-compatible sandbox with a trusted single maker and custodial deposit-address keys. No real assets should ever be sent there. Notch must distinguish the two in the product, README and demo.

## 6. Differentiation and competitive positioning

| Reference | Lesson | Notch choice |
|---|---|---|
| Trendr / Zora-style attention products | Attention can become a consumer financial primitive. | Focus on transparent measurement, simple stakes and proof. |
| Eros Markets | Event probabilities can be tradeable over time. | Start with bounded time-limited markets instead of complex probability perps. |
| Amplifi | Cross-chain funding removes friction. | Use an Intents-shaped funding proof with a separate settlement contract. |
| Hunch / basic prediction markets | Questions can be understandable and shareable. | Add stronger source definitions, receipts and trend research. |
| Copycat / private strategy products | Traders value selectively revealing information. | Private research now; selective disclosure and sealed positions later. |
| NEAR ecosystem | Cross-chain execution and privacy are strategic primitives. | Use a NEAR-first architecture with honest privacy boundaries. |

### Positioning hypothesis

> A consumer attention-market app where every outcome has evidence.

Distinctiveness is a hypothesis to validate against fresh NEAR submissions. It is not a claim that no direct competitor exists.

## 7. Value, distribution and economics

### Value to users and NEAR

- **Consumers:** Research, participation and receipts in one explainable product.
- **NEAR:** Testnet contract usage, a reproducible Intents demonstration, AI integration and shareable entry points to the ecosystem.
- **Communities:** Simple topical market links with public outcomes. Creator markets come later, after oracle-abuse controls.
- **Researchers:** A foundation for credible, attributed trend-data products.

### Go-to-market sequence

1. Create a small set of curated markets with accessible topics and frozen rules.
2. Make market-detail pages shareable on X and in NEAR builder communities.
3. Use brief explainers to make each market interesting to non-traders.
4. Measure wallet connection, first position, settled claims and return visits.
5. Expand to community market creation only after market integrity is robust.

### Potential future revenue, not testnet revenue

After legal and security review, possible revenue streams include clearly disclosed trading fees, advanced research subscriptions and paid market-data APIs. Fees remain zero in the hackathon accounting design to reduce complexity.

A mainnet prediction-market product may trigger licensing, geofencing, KYC/AML, market-abuse, derivatives or gambling requirements depending on jurisdiction.

## 8. Roadmap and success definition

| Stage | Target capabilities | Success signal |
|---|---|---|
| P0 hackathon core | Both modes, public testnet contract, test USDC, deterministic resolution and claims, valid Intents demo and receipts. | A judge can enter, resolve and claim real testnet positions. |
| P1 consumer layer | NEAR AI briefs, market pages, Portfolio, share cards, onboarding and private watchlists. | A new user understands and completes the flow without assistance. |
| P2 stretch | Hidden-until-reveal positions in sealed markets, secret-recovery guidance and non-reveal rules. | Choice secrecy is demonstrated without falsely hiding wallets or amounts. |
| V2 after hackathon | True secondary trading, multi-source attention index, selective disclosure and confidential funding. | Evidence of sustained use, viable liquidity and legal clearance. |
| V3 longer horizon | Community markets, analytics APIs, creator incentives, risk controls and production operations. | Repeat market usage with measurable trust and revenue. |

## Five non-negotiables for the demo

1. Both market types actually accept positions on NEAR testnet.
2. A deterministic settlement path is independently reproducible.
3. A real Intents-compatible testnet swap is shown, or the blocker is disclosed rather than mocked.
4. All sources, privacy scope and simulated data are labeled honestly.
5. The public repository and video exactly match the working implementation.

### Timing note

The source planning document records a submission deadline of 14 November 2026 at 23:59 UTC, equivalent to 15 November at 00:59 WAT. The public repository, demo post and NEAR payout address are required according to the cited submission material. Recheck the live submission page before publication.

## Sources

- [Official NEAR Hackathon site](https://nearhackathon.com/)
- [NEAR Hackathon guide and starter resources](https://github.com/nearai/near-hackathon-prompt-examples)
- [Unstoppable DeFi track](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/tracks/01-defi.md)
- [Open Innovation track](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/tracks/13-open.md)
- [Submission checklist](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/SUBMITTING.md)
- [NEAR Intents 1Click quickstart](https://docs.agentsonintents.com/integration/distribution-channels/1click-api/quickstart/introduction)
- [Tidepool documentation](https://www.usetidepool.tech/docs)
- [Tidepool quickstart](https://www.usetidepool.tech/docs/quickstart)
- [Wikimedia Analytics API documentation](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/getting-started.html)
- [Wikimedia access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html)
- [YouTube Data API quotas](https://developers.google.com/youtube/data/determine_quota_cost)
- [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [NEAR AI pricing](https://near.ai/pricing)
