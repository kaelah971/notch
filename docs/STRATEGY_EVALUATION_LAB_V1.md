# Phase 5D — Strategy Evaluation Lab V1

The Evaluation Lab replays saved `notch.strategy/1` definitions against genuine,
frozen Wikimedia observations. It is a historical research surface only:
results are hypothetical signals, not trading profitability, token returns,
positions, on-chain predictions, or evidence that future outcomes are likely.

## Evaluation contract

For each possible decision date, the evaluator constructs:

1. a complete previous attention window;
2. a complete current attention window ending at the decision cutoff;
3. a complete following target window used only after the signal is issued.

The signal reads only the previous/current windows. The target window is used to
score an already-issued prediction. Missing observations are never imputed. A
zero-valued previous window is reported as `ZERO_BASELINE` and is not passed to
the percentage-growth calculation.

The evaluator records:

- candidate and eligible windows;
- triggered signals, correct/incorrect outcomes, skipped windows, and unavailable
  windows;
- accuracy with explicit `n`;
- Always-UP on the same triggered signal dates;
- percentage-point difference from that baseline;
- every decision's cutoff, windows, sums, momentum, threshold, prediction and
  observed outcome;
- schema, methodology, dataset version and integrity hash;
- a deterministic result digest.

Adjacent candidate windows advance one UTC day and overlap. The UI discloses the
full overlap span so window counts are not presented as independent trials.

## Dataset boundary

V1 has one genuine browser fixture:

- Topic: Nvidia
- Dataset: `wikimedia-nvidia-2026-10-01-2026-11-10`
- Version: `1`
- Source: Wikimedia Analytics API, English Wikipedia, all-access, user,
  daily pageviews
- Dataset SHA-256:
  `4661cc83a880931a392d3745fe234869bae3f191b4bff4229cb6ad2682175cfd`
- Source fixture: `services/oracle/fixtures/pageviews_Nvidia.json`

Other supported Builder topics, such as Bitcoin or ChatGPT, return an explicit
unsupported-dataset state until a genuine frozen fixture is added. Long
horizons return an insufficient-data state rather than fabricating observations.

## Reproducible example

Hypothesis:

> If Nvidia attention falls by at least 5% over the previous 7 days, predict
> DOWN for the next 7 days; if data is missing, do not signal.

Compiled rule (saved name: `Nvidia falling attention / 5%`):

- source: Wikimedia Pageviews V1 / Nvidia;
- signal: `FALLING`, threshold `500 bps`;
- signal window: previous 7 complete UTC days versus current 7 complete UTC
  days;
- target: following 7 complete UTC days;
- missing-data policy: `NO_SIGNAL`;
- strategy identity: `strategy_d7382362`;
- strategy revision hash: `fnv1a32:ebf6ab01`;
- evaluation result digest: `fnv1a32:5ad1d64d`.

Result over the frozen 2026-10-01 through 2026-11-10 observations:

- candidate windows: 21;
- eligible windows: 21;
- triggered signals: 8;
- correct: 5;
- incorrect: 3;
- accuracy: 62.5% (`n=8`);
- Always-UP on those same 8 signal dates: 37.5% (`n=8`);
- difference: +25.0 percentage points;
- skipped below-threshold windows: 13;
- unavailable windows: 0.

The eight signal dates are 2026-10-27 through 2026-11-03. Five DOWN calls
matched the subsequent target-window outcome; the final three did not. This is a
small, overlapping, single-topic sample and is not a general performance claim.
The `fnv1a32` labels are deterministic local identity/digest labels, not
cryptographic attestations; the dataset's SHA-256 remains the source integrity
value.

## Comparison behavior

The Lab can compare two saved rules on the same frozen fixture. It reports:

- matched eligible windows;
- matched triggered dates;
- each rule's own coverage, sample size, accuracy, and Always-UP baseline;
- warnings when eligible or triggered populations differ.

It does not claim that one rule outperforms another when their evaluated
populations differ. The baseline is always aligned to the strategy's own
triggered signal dates.

## Safety boundary

The Lab does not call NEAR AI, access a wallet, sign, submit transactions,
publish a market, create an entry intent, settle a market, or write to Forecast
Passport, Pulse, Social Discovery, or trader rankings. Saved strategies and
lab selections remain device-local.
