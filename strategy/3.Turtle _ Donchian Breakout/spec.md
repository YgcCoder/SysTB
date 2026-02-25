# Base Strategy Doc — Turtle / Donchian Breakout (Daily)
**Strategy ID:** turtle_donchian_daily_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Indicator families: Donchian Channels + ATR (N)
- Breakout entry logic, pyramiding increments, and stop logic
- Execution timing assumptions (see Section 7)
- Position mode (Long / Short / Flat)
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Donchian breakout window (entry channel length)
- Exit channel length (optional)
- ATR window length
- Risk fraction per unit (position sizing) and pyramiding cap
- Stop distance multiples (e.g., 2N) and add-on threshold (e.g., 0.5N)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement the classic Turtle trend-following system using:
- Donchian channel breakouts for entry
- ATR (a.k.a. N) for volatility-adjusted sizing, pyramiding, and stops

This benchmark tests whether a model can correctly implement:
- multi-step stateful logic (units, add-on levels, trailing stop updates)
- symmetric long/short handling
- deterministic bar-by-bar execution and full auditability
- no look-ahead

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

## 3) Indicator Module
### 3.1 Donchian Channels (Frozen)
Let:
- `L_entry` be the entry channel lookback length
- `L_exit` be the exit channel lookback length

Define:
- Entry upper breakout level:
  - `DC_high_t = MAX(high_{t-L_entry+1 ... t})`
- Entry lower breakout level:
  - `DC_low_t  = MIN(low_{t-L_entry+1 ... t})`

Optional exit channels:
- Long exit level:
  - `DC_exit_long_t  = MIN(low_{t-L_exit+1 ... t})`
- Short exit level:
  - `DC_exit_short_t = MAX(high_{t-L_exit+1 ... t})`

> Note: To avoid look-ahead, use fully-formed bars only.

### 3.2 ATR (N) (Frozen)
Compute True Range:
- `TR_t = MAX( high_t - low_t, ABS(high_t - close_{t-1}), ABS(low_t - close_{t-1}) )`

ATR (N):
- `N_t = SMA(TR, L_atr)`  (rolling mean of TR)

---

## 4) Signal Module
### 4.1 Entry Signals (Frozen Logic)
Entry is based on Donchian breakout levels evaluated at bar close.

**Enter Long** at bar `t` close if:
- `close_t > DC_high_t`
- AND current position is not long (i.e., state is Flat or Short)

**Enter Short** at bar `t` close if:
- `close_t < DC_low_t`
- AND current position is not short (i.e., state is Flat or Long)

> Reversal is allowed: if in the opposite direction, close then enter (see priority rules).

---

### 4.2 Pyramiding (Add-on) (Frozen Logic)
Once in a position, add units when price moves favorably by `add_step_mult * N_entry`.

Let:
- `N_entry` = ATR value (`N_t`) at the time the first unit was opened
- `add_step = add_step_mult * N_entry`
- `last_add_price` = price level of the most recent unit entry (initially the first entry price)

**For Long positions:**
- If `close_t >= last_add_price + add_step` AND units < `max_units`:
  - Add one unit (increase position)

**For Short positions:**
- If `close_t <= last_add_price - add_step` AND units < `max_units`:
  - Add one unit

After adding:
- Update `last_add_price` to the price used for the add-on entry
- Update trailing stop level per Section 5.2

---

### 4.3 Exit Signals (Frozen Logic)
Two exits exist, both evaluated at bar close:

**A) Stop Loss (primary risk exit):**
- Long: exit if `close_t <= stop_level_t`
- Short: exit if `close_t >= stop_level_t`

**B) Channel Exit (trend exit, optional but enabled by default):**
- Long: exit if `close_t < DC_exit_long_t`
- Short: exit if `close_t > DC_exit_short_t`

---

### 4.4 Signal Priority (Frozen)
On the same bar, apply in this order:
1) Stop-loss exit  
2) Channel exit  
3) Reversal entry (close opposite, then enter)  
4) Add-on (pyramiding)  

No simultaneous long and short positions are allowed.

---

## 5) Position & Risk Module
### 5.1 Position Mode (Frozen)
- Allowed states: `Long`, `Short`, `Flat`
- At most one active position per instrument
- Position consists of integer **units** (1..max_units)

### 5.2 Sizing & Units (Frozen Semantics, Tunable Parameters)
Define:
- `risk_fraction` = fraction of equity risked per unit (tunable)
- `stop_mult` = stop distance in units of N_entry (tunable)

At initial entry:
- Determine `N_entry = N_t` (ATR on entry bar)
- Define stop distance:
  - `stop_dist = stop_mult * N_entry`

Stop level:
- For Long:
  - `stop_level = entry_price - stop_dist`
- For Short:
  - `stop_level = entry_price + stop_dist`

After each add-on, stop level is adjusted by the same directional step:
- Long: stop_level increases by `add_step` after each add-on
- Short: stop_level decreases by `add_step` after each add-on

> This captures the classic Turtle behavior where each add-on effectively “ratchets” the stop.

### 5.3 Max Units (Frozen Semantics)
- `max_units` is tunable but capped (default 4 units, consistent with classic pyramiding).

---

## 6) Execution Module (Frozen)
Backtest execution assumptions:
- Signals are evaluated at **bar close**.
- Orders are executed at the **same bar close**.
- Default: no slippage, no commission (unless harness applies them).

---

## 7) Edge Cases (Frozen)
- If indicators are undefined: no signal.
- If both stop-loss and channel exit trigger on the same bar: stop-loss takes precedence.
- If reversal entry triggers, do not also pyramid on the same bar.
- If multiple add-on conditions would be satisfied (gap moves): add **at most one unit per bar**.

---

## 8) Required Outputs (Mandatory)
The implementation MUST emit:

### 8.1 Trade Log (per completed trade)
A “trade” is one full position lifecycle (Flat → (Long/Short with units) → Flat).
Required fields:
- `trade_id`
- `instrument`
- `side` (`"long"` or `"short"`)
- `entry_time`, `entry_price`
- `exit_time`, `exit_price`
- `avg_entry_price` (unit-weighted)
- `units_max` (max units reached)
- `pnl`, `pnl_pct`
- `reason_entry` (`"donchian_breakout_long"` / `"donchian_breakout_short"`)
- `reason_exit` (`"stop_loss"` / `"channel_exit"` / `"reversal"`)

### 8.2 Fill-Level Log (Mandatory for pyramiding)
For each unit add-on (including initial):
- `fill_time`
- `fill_price`
- `fill_units_delta` (+1 or -1 in unit terms)
- `units_after`
- `stop_level_after`

### 8.3 Per-bar Audit Log (recommended)
At minimum per bar:
- `datetime`, `close`
- `DC_high`, `DC_low`, `DC_exit_long`, `DC_exit_short`
- `TR`, `N_t`
- `signal`
- `position_state`, `units`, `stop_level`, `last_add_price`
- `equity`

### 8.4 Summary Metrics
- total_return
- annualized_return
- max_drawdown
- win_rate
- num_trades

---

## 9) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `L_entry`, `L_exit`, `L_atr`
- `add_step_mult`, `stop_mult`
- `max_units`
- `risk_fraction` (if harness uses it)

Constraints:
- `L_entry >= 10`, `L_exit >= 5`, `L_atr >= 10`
- `max_units` in [1, 8]
- `add_step_mult > 0`, `stop_mult > 0`
- Symmetric rules must hold for long and short.

The model MUST NOT:
- change the breakout/crossover semantics
- add new indicators
- use future data
