# Base Strategy Doc — Double Moving Average Crossover (Daily)
**Strategy ID:** dma_crossover_daily_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Indicator family: Simple Moving Averages (SMA)
- Crossover-based entry and exit semantics
- Execution timing assumptions (see Section 6)
- Position mode (Long / Short / Flat)
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Short moving average window `N_short`
- Long moving average window `N_long`
- Optional stop-loss percentage `stop_loss_pct`
- Optional transaction cost assumptions (if enabled by the harness)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a classic **trend-following** strategy using a **double moving average crossover**
on **daily bars**.

The strategy is designed to test whether a model can:
- correctly implement indicator-based crossover logic
- handle symmetric long/short rules
- maintain consistent position state
- respect execution and audit constraints

---

## 2) Data Module
### 2.1 Input (Required)
- Frequency: `1d`
- Fields (must exist):
  - `datetime`, `open`, `high`, `low`, `close`, `volume`

### 2.2 Data Rules
- Bars must be sorted by `datetime` ascending.
- Missing bars: skip signal generation on that bar.
- Insufficient lookback: do not compute indicators or generate signals.

---

## 3) Indicator Module (Double Moving Average)
### 3.1 Definitions (Frozen)
Let:
- `N_short` be the short moving average window
- `N_long` be the long moving average window  
with the constraint: `N_short < N_long`.

- Short moving average:
  - `SMA_short_t = SMA(close, N_short)`
- Long moving average:
  - `SMA_long_t = SMA(close, N_long)`

---

### 3.2 Default Parameters (Tunable)
- `N_short = 20`
- `N_long = 60`

---

## 4) Signal Module
### 4.1 Entry Signals (Frozen Logic)

**Enter Long** at bar `t` close if:
- `SMA_short_t > SMA_long_t`
- AND `SMA_short_{t-1} <= SMA_long_{t-1}`

(Upward crossover / golden cross)

---

**Enter Short** at bar `t` close if:
- `SMA_short_t < SMA_long_t`
- AND `SMA_short_{t-1} >= SMA_long_{t-1}`

(Downward crossover / death cross)

---

### 4.2 Exit Logic (Frozen)
This strategy uses **full reversal** semantics:

- A long position is closed **only** when a valid short entry signal occurs.
- A short position is closed **only** when a valid long entry signal occurs.

There is no independent take-profit signal.

---

### 4.3 Signal Priority (Frozen)
On the same bar:
1) Stop-loss exit (if enabled and triggered)  
2) Reversal entry (which implicitly exits the opposite position)  

No simultaneous long and short positions are allowed.

---

## 5) Position & Portfolio Module
### 5.1 Position Mode (Frozen)
- Allowed states: `Long`, `Short`, `Flat`
- At most one active position per instrument.

### 5.2 Sizing (Frozen Default)
- Single-instrument benchmark sizing: `100%` of allocated capital.
- All-in / all-out on each signal.
- No pyramiding, no partial scaling.

---

## 6) Risk Module
### 6.1 Stop Loss (Optional, Tunable parameter)
A symmetric percentage-based stop loss may be enabled.

For a **long** position:
- Trigger if `close_t <= entry_price * (1 - stop_loss_pct)`

For a **short** position:
- Trigger if `close_t >= entry_price * (1 + stop_loss_pct)`

Default:
- `stop_loss_pct = null` (disabled)

If enabled and triggered:
- Immediately `EXIT_POSITION` at bar `t` close.

---

### 6.2 Additional Risk Constraints (Frozen)
- No look-ahead.
- Indicator values must be fully available before signal evaluation.

---

## 7) Execution Module (Frozen)
Backtest execution assumptions:
- Signals are evaluated at **bar close**.
- Orders are executed at the **same bar close**.
- Default: no slippage, no commission (unless harness applies them).

---

## 8) Edge Cases (Frozen)
- Repeated crossover signals while already in the same direction: ignore.
- If both stop-loss and reversal occur on the same bar: stop-loss takes priority.
- Data gaps or undefined indicators: no signal emitted.

---

## 9) Required Outputs (Mandatory)
The implementation MUST emit:

### 9.1 Trade Log (per completed trade)
Required fields:
- `trade_id`
- `instrument`
- `entry_time`, `entry_price`
- `exit_time`, `exit_price`
- `side` (`"long"` or `"short"`)
- `quantity` or `notional` (follow harness convention)
- `pnl`, `pnl_pct`
- `reason_entry` (`"golden_cross"` / `"death_cross"`)
- `reason_exit` (`"reverse_signal"` / `"stop_loss"`)

---

### 9.2 Per-bar Audit Log (recommended)
At minimum per bar:
- `datetime`
- `close`
- `SMA_short_t`, `SMA_long_t`
- `signal`
- `position_state`
- `equity`

---

### 9.3 Summary Metrics
- total_return
- annualized_return
- max_drawdown
- win_rate
- num_trades

---

## 10) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `N_short`, `N_long`
- `stop_loss_pct`

Constraints:
- `N_short < N_long` must always hold.

The model MUST NOT:
- introduce additional indicators
- alter crossover semantics
- use asymmetric logic between long and short
- introduce look-ahead or future data
