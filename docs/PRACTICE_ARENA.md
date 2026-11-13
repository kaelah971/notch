# Notch Practice Arena V1

Practice Arena is a walletless learning surface. It reads the existing published market catalogue, but it never connects a wallet, requests an entry intent, signs, broadcasts, funds, settles, or writes to NEAR.

## Practice accounting

Every browser starts with **1,000 practice credits**. A device may record at most one practice call per market. Stakes are whole-number credits and are reserved from the available balance when the call is pending or the finalized result is unknown.

The deliberately simple learning score is:

- `CORRECT`: release the stake and add an equal virtual reward (`+2 × stake` to available credits from the original reservation);
- `INCORRECT`: spend the stake;
- `VOIDED`: refund the stake;
- `PENDING` and `UNKNOWN`: keep the stake reserved.

This is not a parimutuel payout, profit figure, test-USDC balance, or estimate of real returns. Practice records are never included in Pulse, Forecast Passport, Social Discovery, or verified trader rankings.

## Result classification

Practice results are derived only from the current published market state:

- open or closed markets are `PENDING`;
- a void/tie resolution is `VOIDED`;
- a resolved market must expose `winning_outcome`, `resolution_kind=winning_outcome`, and available evidence before it can be `CORRECT` or `INCORRECT`;
- missing market data, evidence, winner, or an original choice is `UNKNOWN`.

Live practice calls are accepted only while the market is open and before the API's authoritative `close_at_utc`. Resolved historical demonstrations may be replayed, but the UI labels them as test/demo data and they are not participant activity.

## Local storage and sharing

State is stored under `notch.practice.arena.v1` in the browser's local storage. It is not synced, authenticated, recoverable across cleared browser data, or evidence of an onchain position. Shared cards say **Practice**, use practice credits, and say local-only/no wallet; they do not claim transaction or contract verification.

## Deterministic verification

`web/tests/practice.test.mjs` uses explicit market fixtures labelled as test data. The fixtures cover pending, correct, incorrect, voided, unknown, budget validation, duplicates, deadline rejection, persistence, accuracy, streaks, and practice share-card labelling. They do not represent real participant activity.

## Practice Backtesting V1

Historical Replay is a separate, read-only research sandbox inside Practice Arena. It does not create local practice positions, change the virtual-credit ledger, call the wallet layer, or write to the chain.

The shipped fixture is a 41-day subset of the recorded real Wikimedia Analytics response for `Nvidia` pageviews (`en.wikipedia.org`, all-access, user agent), covering `2026-10-01` through `2026-11-10`. The source is `services/oracle/fixtures/pageviews_Nvidia.json`, recorded on `2026-11-12T01:40:00Z`; the raw source fixture SHA-256 is `f372687814e75ca213ef31e014a2a9a8dc204340f249a44922ae9e1401e436f2`. The browser fixture's canonical content SHA-256 is `4661cc83a880931a392d3745fe234869bae3f191b4bff4229cb6ad2682175cfd`. These are historical observations, not fabricated market results or participant activity.

The default strategy is **seven-day attention momentum**:

1. At a signal date, compare the latest seven-day pageview sum with the preceding seven-day sum.
2. Predict `UP` when growth is at least the selected threshold, `DOWN` when it is at most the negative threshold, and record no signal inside the band. At the `0%` option, exactly zero growth is treated as no signal so it cannot satisfy both directions.
3. Evaluate that prediction against the following seven observed days (`UP` when the forward sum is at least the signal-window sum).

The target window starts after the signal date. It is never used to generate the signal. Missing observations are reported as unavailable and are never imputed. The bounded UI exposes only `0`, `5%`, `10%`, `15%`, and `20%` thresholds. The baseline is **Always UP on the same eligible signal dates**, so the comparison uses the same sample rather than a different coverage window.

For the default `5%` threshold, the deterministic replay has 21 candidate dates, 16 eligible signals, 7 correct, 9 incorrect, and `43.8%` strategy accuracy. The same-date baseline is 5 correct of 16 (`31.3%`), a `+12.5pp` difference. This is one frozen-sample result, not evidence of predictive performance or a promise of future returns.

`web/tests/backtest.test.mjs` verifies fixture integrity, deterministic results, exact threshold boundaries, missing-data handling, no-lookahead window ordering, empty-sample behavior, and the absence of signer/entry-intent dependencies from the Practice page. Backtest rows remain outside Practice Portfolio, Pulse, Forecast Passport, Social Discovery, and rankings.

## Future bounded extensions

A later milestone can add more versioned frozen datasets and explicitly labelled strategy comparisons without touching live accounts. An AI Agent Arena should remain a separate sandbox: agents can submit the same local practice action contract, while every generated decision and score is labelled simulated and cannot enter onchain, Pulse, Passport, or settlement paths.
