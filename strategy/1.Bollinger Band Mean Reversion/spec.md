# Base Strategy Doc — Bollinger Band Mean Reversion (Daily)
**Strategy ID:** bb_mr_daily_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Indicator family: Bollinger Bands (SMA + rolling STD)
- Entry/Exit semantics and crossing logic
- Execution timing assumptions (see Section 6)
- Position mode (Long/Flat only)
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Bollinger window length `N`
- Band width multiplier `k`
- Stop-loss percentage `stop_loss_pct`
- Optional transaction cost assumptions (if the harness enables them)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a classic **mean-reversion** strategy using Bollinger Bands on **daily bars**.  
The strategy enters long after a **downward crossing** below the lower band and exits when price **reverts to the middle band** (or triggers stop-loss).

Primary evaluation focuses on:
- correctness and determinism
- no look-ahead
- consistent execution and complete audit logs

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

## 3) Indicator Module (Bollinger Bands)
### 3.1 Definitions (Frozen)
Let `N` be the rolling lookback window and `k` be the band multiplier.

- Middle band:
  - `MB_t = SMA(close, N)`
- Rolling standard deviation:
  - `SD_t = STD(close, N)`
- Upper band:
  - `UB_t = MB_t + k * SD_t`
- Lower band:
  - `LB_t = MB_t - k * SD_t`

### 3.2 Default Parameters (Tunable)
- `N = 20`
- `k = 2.0`

---

## 4) Signal Module
### 4.1 Entry Signal (Frozen Logic)
**Enter Long** at bar `t` close if the following crossing condition holds:

- `close_t < LB_t` AND `close_{t-1} >= LB_{t-1}`

Interpretation: a valid **downward cross** below the lower band.

### 4.2 Exit Signal (Frozen Logic)
**Exit (Close Position)** at bar `t` close if:

- `close_t >= MB_t`

Interpretation: price reverted to the mean.

### 4.3 Signal Priority (Frozen)
On the same bar:
1) Stop-loss exit (if triggered)  
2) Mean-reversion exit  
3) Entry signal  

No simultaneous enter-and-exit on the same bar; exits win.

---

## 5) Position & Portfolio Module
### 5.1 Position Mode (Frozen)
- Long / Flat only (no short selling).
- At most one active position per instrument.

### 5.2 Sizing (Frozen Default)
- Single-instrument benchmark sizing: `100%` of allocated capital (all-in / all-out).
- No pyramiding / no scaling in/out.

(If your harness enforces notional sizing, align to its conventions, but do not change the semantics.)

---

## 6) Risk Module
### 6.1 Stop Loss (Tunable parameter, Frozen semantics)
Stop-loss is defined as a percentage drawdown from entry price.

Trigger at bar `t` close if:
- `close_t <= entry_price * (1 - stop_loss_pct)`

Default:
- `stop_loss_pct = 0.10`

Action:
- `EXIT_POSITION` at bar `t` close.

### 6.2 Additional Risk Constraints (Frozen)
- No trading when indicator values are undefined.
- No look-ahead (do not use future bars for any computation).

---

## 7) Execution Module (Frozen)
Backtest execution assumptions:
- Signals are evaluated at **bar close**.
- Orders are executed at the **same bar close** (close-to-close execution).
- Default: no slippage, no commission (unless harness explicitly applies them).

---

## 8) Edge Cases (Frozen)
- Repeated entry while already long: ignore.
- If data gaps prevent indicator computation: no signal emitted.
- If both entry and exit conditions appear on the same bar: exit wins (per priority rules).

---

## 9) Required Outputs (Mandatory)
The implementation MUST emit:

### 9.1 Trade Log (per completed trade)
Required fields:
- `trade_id`
- `instrument`
- `entry_time`, `entry_price`
- `exit_time`, `exit_price`
- `side` (must be `"long"` for this strategy)
- `quantity` or `notional` (follow harness convention)
- `pnl`, `pnl_pct`
- `reason_entry` (e.g., `"lb_cross_down"`)
- `reason_exit` (e.g., `"mb_revert"` or `"stop_loss"`)

### 9.2 Per-bar Audit Log (recommended, if harness supports)
At minimum per bar:
- `datetime`
- `close`
- `MB_t`, `UB_t`, `LB_t`
- `signal` (none/enter/exit)
- `position_state` (flat/long)
- `equity` (portfolio value)

### 9.3 Summary Metrics
- total_return
- annualized_return
- max_drawdown
- win_rate
- num_trades

---

## 10) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `N`, `k`, `stop_loss_pct` (within bounds defined in the JSON spec)

The model MUST NOT:
- add new indicators
- alter crossing logic
- introduce short selling
- use future data
