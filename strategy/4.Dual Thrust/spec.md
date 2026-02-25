# Base Strategy Doc — Dual Thrust (Intraday Replay)
**Strategy ID:** dual_thrust_intraday_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Indicator family: Dual Thrust breakout bands derived from prior daily OHLC
- Band construction logic (HH/HC/LC/LL -> Range -> upper/lower lines)
- Intraday execution semantics and daily reset behavior
- Position mode (Long / Short / Flat), reversal behavior
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Lookback days `N_days` used for Range
- Band multipliers `k1`, `k2`
- Intraday bar frequency for replay (e.g., 15m by default; 1h optional)
- Optional stop-loss / time-based close policy (if explicitly enabled in JSON spec)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement the classic **Dual Thrust** intraday breakout system in an **offline replay**
setting using numerical OHLCV data only.

The strategy:
- Computes daily breakout levels from the prior `N_days` daily bars
- Trades intraday when price crosses these levels
- Uses reversal semantics (close opposite then enter new direction)
- Resets state daily

Primary evaluation focuses on:
- correct daily band computation without look-ahead
- correct intraday signal evaluation and reversal handling
- deterministic replay behavior and complete audit logs

---

## 2) Data Module
### 2.1 Inputs (Required)
This strategy requires **two aligned data streams**:

#### A) Daily bars (for Range computation)
- Frequency: `1d`
- Fields: `datetime, open, high, low, close, volume`

#### B) Intraday bars (for trading)
- Frequency: `intraday` (default `15m`, derived from raw 1m resampling if needed)
- Fields: `datetime, open, high, low, close, volume`

### 2.2 Alignment Rules (Frozen)
- Each intraday bar belongs to exactly one trading date `D`.
- Daily bars used for Range on date `D` must come strictly from **dates < D**.
- The intraday "day open" used in band construction must be the **open price of the first intraday bar** of date `D`.

### 2.3 Missing Data Policy (Frozen)
- If the first intraday bar of a day is missing, skip the day (no trading).
- If insufficient daily history for Range, skip the day.
- If intraday gaps occur within the day, signals are evaluated only on available bars.

---

## 3) Indicator / Band Module (Dual Thrust)
### 3.1 Definitions (Frozen)
Given daily history over the prior `N_days` days (strictly before date `D`):

- `HH = MAX(high)`
- `HC = MAX(close)`
- `LC = MIN(close)`
- `LL = MIN(low)`

Compute:
- `Range = MAX(HH - LC, HC - LL)`

Let `Open_D` be the day open (open of first intraday bar on date `D`).

Breakout bands for date `D`:
- Upper line: `BuyLine_D  = Open_D + k1 * Range`
- Lower line: `SellLine_D = Open_D - k2 * Range`

---

## 4) Signal Module
Signals are evaluated on **intraday bar close**.

### 4.1 Entry / Reversal (Frozen Logic)
At intraday bar `t` on date `D`:

**Enter / Hold Long**
- If `close_t > BuyLine_D`:
  - If position is Long: do nothing
  - If position is Short: close short, then enter long
  - If Flat: enter long

**Enter / Hold Short**
- Else if `close_t < SellLine_D`:
  - If position is Short: do nothing
  - If position is Long: close long, then enter short
  - If Flat: enter short

**Otherwise**
- Hold (no action)

### 4.2 Daily Reset (Frozen)
- Positions may be carried intraday across bars within the same date `D`.
- End-of-day behavior is controlled by `eod_close_policy` (see Section 6).
  - Default for benchmark: **close all positions at end of day** (no overnight).

### 4.3 Signal Priority (Frozen)
On a bar where both conditions might appear due to malformed inputs:
1) If `close_t > BuyLine_D` and `close_t < SellLine_D` cannot both be true under normal bands.  
2) If data is inconsistent, treat as **no-trade** for that bar and log an anomaly.

Stop-loss (if enabled) overrides entry/reversal.

---

## 5) Position & Portfolio Module
### 5.1 Position Mode (Frozen)
- Allowed states: `Long`, `Short`, `Flat`
- At most one active position per instrument.

### 5.2 Sizing (Frozen Default)
- Single-instrument sizing: `100%` of allocated capital (all-in / all-out).
- No pyramiding, no partial scaling.

---

## 6) Risk & Close Policy
### 6.1 End-of-Day Close (Frozen semantics, Tunable switch)
To avoid overnight assumptions in an intraday benchmark, the default is:

- `eod_close_policy = "close_all"`

Definition:
- On the final intraday bar of date `D`, if position != Flat:
  - Exit at that bar close.

### 6.2 Optional Stop Loss (Optional, Tunable)
A symmetric percentage stop-loss may be enabled:

- For Long: `close_t <= entry_price * (1 - stop_loss_pct)`
- For Short: `close_t >= entry_price * (1 + stop_loss_pct)`

Default:
- `stop_loss_pct = null` (disabled)

If enabled and triggered:
- Exit at bar close.

---

## 7) Execution Module (Frozen)
- Signals are evaluated at **intraday bar close**.
- Orders are executed at the **same intraday bar close**.
- Default: no slippage, no commission (unless harness applies them).

---

## 8) Edge Cases (Frozen)
- If day open cannot be determined: skip day.
- If insufficient daily history for Range: skip day.
- One action per bar: if reversal occurs, do not also apply EOD close on the same bar (EOD close is only for the last bar).
- If stop-loss and reversal both occur on the same bar: stop-loss exit takes priority.

---

## 9) Required Outputs (Mandatory)
### 9.1 Trade Log (per completed trade)
Required fields:
- `trade_id`
- `instrument`
- `side` (`"long"` or `"short"`)
- `entry_time`, `entry_price`
- `exit_time`, `exit_price`
- `pnl`, `pnl_pct`
- `reason_entry` (`"breakout_buyline"` / `"breakout_sellline"` / `"reversal"`)
- `reason_exit` (`"reversal"` / `"eod_close"` / `"stop_loss"`)

### 9.2 Daily Band Log (Mandatory)
For each trading date `D`:
- `date`
- `Open_D`
- `HH`, `HC`, `LC`, `LL`
- `Range`
- `BuyLine_D`, `SellLine_D`

### 9.3 Per-bar Audit Log (recommended)
At minimum:
- `datetime`, `close`
- `BuyLine_D`, `SellLine_D`
- `signal`
- `position_state`
- `equity`

### 9.4 Summary Metrics
- total_return
- annualized_return
- max_drawdown
- win_rate
- num_trades

---

## 10) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `N_days`
- `k1`, `k2`
- `intraday_frequency` (15m vs 1h)
- `stop_loss_pct` (if enabled)
- `eod_close_policy` may be `"close_all"` or `"hold_overnight"` only if the harness explicitly supports overnight accounting.
  - Default remains `"close_all"`.

The model MUST NOT:
- change the Range formula
- use current-day daily OHLC to compute Range for that same day
- add new indicators
- introduce pyramiding
- use future data
