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

## Future bounded extensions

A later milestone can add strategy backtesting by importing a versioned market/result fixture set and replaying a strategy against frozen rules without touching live accounts. An AI Agent Arena should remain a separate sandbox: agents can submit the same local practice action contract, while every generated decision and score is labelled simulated and cannot enter onchain, Pulse, Passport, or settlement paths.
