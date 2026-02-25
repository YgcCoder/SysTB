# Base Strategy Doc — R-Breaker (Intraday Replay)
**Strategy ID:** rbreaker_intraday_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- R-Breaker level construction from prior day (H, L, C) using the specified formulas
- Regime logic: breakout when flat; reversal logic when in position
- Intraday execution semantics and daily reset behavior
- Position mode (Long / Short / Flat) and reversal behavior
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Optional stop-loss threshold (points or percentage)
- Intraday bar frequency for replay (default 15m; optional 1h)
- End-of-day close policy (default close all)
- If needed: a minimum time after open before signals are allowed (optional, if harness supports)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement the classic **R-Breaker** intraday strategy in an **offline replay** setting.

R-Breaker uses:
- **6 price levels** computed from the previous trading day’s High/Low/Close
- **Breakout mode** when flat (trend-following)
- **Reversal mode** when in a position (mean-reverting reversal after an observation trigger)
- **End-of-day flattening** by default (no overnight positions)

Primary evaluation focuses on:
- correct level calculation without look-ahead
- correct intraday state tracking (observation triggers, reversal conditions)
- deterministic replay execution and complete audit logs

---

## 2) Data Module
### 2.1 Inputs (Required)
Two aligned streams:

#### A) Daily bars (for prior-day H/L/C)
- Frequency: `1d`
- Fields: `datetime, open, high, low, close, volume`

#### B) Intraday bars (for trading)
- Frequency: `intraday` (default `15m`)
- Fields: `datetime, open, high, low, close, volume`

### 2.2 Alignment Rules (Frozen)
For each trading date `D`:
- Prior-day values `H_prev, L_prev, C_prev` must come from the **immediately previous trading day** `< D`.
- Intraday bars on date `D` use the same set of 6 levels computed from `(H_prev, L_prev, C_prev)`.

### 2.3 Missing Data Policy (Frozen)
- If prior-day H/L/C is unavailable: skip day `D` (no trading).
- If intraday data is missing at open: still trade on available bars.
- If intraday gaps: evaluate signals only on available bars.

---

## 3) Level Construction (Frozen)
Let:
- `H = H_prev`, `L = L_prev`, `C = C_prev`
- Pivot:
  - `P = (H + L + C) / 3`

Compute the six R-Breaker levels:

1) **Breakout Buy Price (bBreak)**  
   - `bBreak = H + 2*P - 2*L`

2) **Observation Sell Price (sSetup)**  
   - `sSetup = P + (H - L)`

3) **Reversal Sell Price (sEnter)**  
   - `sEnter = 2*P - L`

4) **Reversal Buy Price (bEnter)**  
   - `bEnter = 2*P - H`

5) **Observation Buy Price (bSetup)**  
   - `bSetup = P - (H - L)`

6) **Breakout Sell Price (sBreak)**  
   - `sBreak = L - 2*(H - P)`

These levels are constant throughout date `D`.

---

## 4) Signal Module
Signals are evaluated on **intraday bar close**, using `close_t` and intraday extremes observed so far.

### 4.1 State Variables (Frozen)
For each day `D`, maintain:
- `position_state ∈ {Flat, Long, Short}`
- `observed_high_D`: maximum intraday high seen so far on date `D`
- `observed_low_D`: minimum intraday low seen so far on date `D`
- `obs_sell_triggered`: whether `observed_high_D > sSetup` has occurred (for long reversal logic)
- `obs_buy_triggered`: whether `observed_low_D < bSetup` has occurred (for short reversal logic)

Update `observed_high_D` and `observed_low_D` each intraday bar using bar high/low.

---

### 4.2 Breakout Mode (when Flat) — Frozen Logic
If `position_state == Flat`:

- **Enter Long** if `close_t > bBreak`
- **Enter Short** if `close_t < sBreak`
- Otherwise: hold flat

---

### 4.3 Reversal Mode (when in Position) — Frozen Logic
#### A) If currently Long
1) First, the observation condition must occur:
   - If `observed_high_D > sSetup`, set `obs_sell_triggered = True`
2) Then, reversal triggers if:
   - `obs_sell_triggered == True` AND `close_t < sEnter`
   - Action: **close long, then enter short** (reversal)

#### B) If currently Short
1) Observation condition:
   - If `observed_low_D < bSetup`, set `obs_buy_triggered = True`
2) Reversal triggers if:
   - `obs_buy_triggered == True` AND `close_t > bEnter`
   - Action: **close short, then enter long** (reversal)

---

### 4.4 Signal Priority (Frozen)
On the same bar, apply in this order:
1) Stop-loss exit (if enabled and triggered)  
2) Reversal (close opposite then enter)  
3) Breakout entry (only if flat)  
4) Otherwise hold

No simultaneous long and short positions are allowed.

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
Default benchmark policy:
- `eod_close_policy = "close_all"`

Definition:
- On the final intraday bar of date `D`, if position != Flat:
  - Exit at that bar close.

### 6.2 Optional Stop Loss (Tunable)
A stop-loss can be enabled as either:
- `points` (absolute price units) OR
- `percentage` (relative to entry)

Default:
- disabled

If `stop_loss_mode == "points"`:
- Long: exit if `entry_price - close_t >= stop_loss_value`
- Short: exit if `close_t - entry_price >= stop_loss_value`

If `stop_loss_mode == "percentage"`:
- Long: exit if `close_t <= entry_price * (1 - stop_loss_value)`
- Short: exit if `close_t >= entry_price * (1 + stop_loss_value)`

Stop-loss exit occurs at bar close.

---

## 7) Execution Module (Frozen)
- Signals are evaluated at **intraday bar close**.
- Orders are executed at the **same intraday bar close**.
- Default: no slippage, no commission (unless harness applies them).

---

## 8) Edge Cases (Frozen)
- If prior-day H/L/C missing: skip day.
- Reset daily state variables at the start of each date `D`:
  - `observed_high_D = -inf`, `observed_low_D = +inf`
  - `obs_sell_triggered = False`, `obs_buy_triggered = False`
- If stop-loss and reversal trigger on the same bar: stop-loss exit takes precedence.
- If reversal triggers, do not also apply breakout entry on the same bar.
- One action per bar.

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
- `reason_entry` (`"breakout_bBreak"` / `"breakout_sBreak"` / `"reversal"`)
- `reason_exit` (`"reversal"` / `"eod_close"` / `"stop_loss"`)

### 9.2 Daily Level Log (Mandatory)
For each trading date `D`:
- `date`
- `H_prev`, `L_prev`, `C_prev`
- `P`
- `bBreak`, `sSetup`, `sEnter`, `bEnter`, `bSetup`, `sBreak`

### 9.3 Per-bar Audit Log (recommended)
At minimum:
- `datetime`, `close`
- all six levels for date `D`
- `observed_high_D`, `observed_low_D`
- `obs_sell_triggered`, `obs_buy_triggered`
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
- `intraday_frequency` (15m vs 1h)
- stop-loss mode/value (if enabled)
- `eod_close_policy` (close_all vs hold_overnight if harness supports)

The model MUST NOT:
- change the six-level formulas
- change the breakout/reversal regime logic
- use future data for level construction
- introduce pyramiding
- add new indicators
