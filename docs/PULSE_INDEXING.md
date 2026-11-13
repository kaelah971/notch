# Notch Pulse indexing

Notch Pulse is a read-only analytics surface. It does not sign, broadcast, fund, settle, or claim anything.

## Source of truth

The indexer reads finalized NEAR RPC blocks, chunks, transaction status, receipt outcomes, and receipt logs. An activity is accepted only when all of these checks pass:

- the outer transaction calls `ft_transfer_call` on `COLLATERAL_TOKEN`;
- the call targets `MARKET_CONTRACT` and contains a valid `market_id` and outcome;
- the final transaction status is successful;
- a successful receipt executes on `MARKET_CONTRACT`;
- the receipt contains a NEP-297-shaped `notch-market / position_entered` event;
- the event amount, market, and outcome match the transfer call;
- the event has a real account, collateral predecessor, finalized receipt block, and timestamp.

Failed transactions, `entry_rejected` events, token balances, pool totals, charts, popularity, and AI output are never counted as calls.

## Cursor and idempotency

`PulseStore` keeps a SQLite cursor and advances it only after the complete block has been scanned and committed. Events use `transaction hash + receipt id + log index` as a durable identity and are inserted with `INSERT OR IGNORE`. A transient RPC error therefore leaves the cursor at the last completed block and can be retried safely.

The default first run establishes a boundary at the current finalized block. It does **not** backfill history. This makes the public coverage claim explicit: Pulse reports activity observed after tracking began. A local operator may set `PULSE_START_BLOCK` to an explicit finalized height when a bounded backfill is intentionally wanted.

Each request scans at most `PULSE_MAX_BLOCKS_PER_REQUEST` blocks (default 25). This is a bounded read-only refresh, not a settlement worker or daemon. A production deployment should run the same indexer from a persistent process/storage volume or an explicitly scheduled job.

## API

`GET /api/pulse?window=7d&refresh=true`

Supported windows are `24h`, `7d`, `30d`, and `all`. The response contains:

- `metrics.forecaster_count`: distinct accounts with accepted entries in the selected indexed window;
- `metrics.new_forecaster_count`: accounts whose first **observed indexed** entry falls in the window;
- `metrics.confirmed_volume_base_units`: sum of accepted event amounts, still in USDC base units;
- `metrics.successful_entries`: unique observed account/market positions (repeated entries in one market count once);
- `metrics.successful_entry_events`: raw count of accepted `position_entered` events;
- `hot_markets`: ranked by confirmed indexed volume, then unique successful positions;
- `participants`: indexed accounts with unique market positions, raw receipt-event count, confirmed volume, and last activity;
- `recent_calls`: finalized event references with transaction, receipt, block, account, market, outcome, and amount;
- `coverage`: tracking boundary, cursor, finality source, and limitations.

`refresh=false` reads the durable snapshot without making an RPC scan. If indexing is not configured, the API returns an explicit `not_configured` coverage state and zero metrics rather than a synthetic feed.

Pulse's social layer uses `participants` for Everyone/Following discovery. Account links open the existing public Signals profile. Following is device-local only; no follower counts or server-side social graph are claimed. Passport accuracy and result badges are read separately from public positions and finalized market state. The leaderboard requires at least three finalized Correct/Incorrect market-level predictions per account; Pending, Voided, Unknown, historical demonstrations, and repeated entries in one market do not qualify or improve a rank.

## Configuration

- `PULSE_DB_PATH` — SQLite path; defaults to `var/web_api/pulse.sqlite3`.
- `PULSE_START_BLOCK` — optional explicit finalized starting height; unset means no historical backfill.
- `PULSE_MAX_BLOCKS_PER_REQUEST` — bounded scan size; defaults to `25` and is capped by the indexer.
- `NEAR_RPC_URL` — the existing read-only NEAR RPC setting.

The web UI keeps Pulse inside the existing Trend Radar surface. It displays coverage and limitations alongside the numbers so an empty or partial index is distinguishable from zero network activity.
