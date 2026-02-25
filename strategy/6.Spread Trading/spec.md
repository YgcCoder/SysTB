# Base Strategy Doc — Spread Trading (Mean-Reversion, Replay-Friendly)
**Strategy ID:** spread_trading_basic_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Strategy class: two-leg spread trading with market-neutral exposure
- Spread definition and normalization method
- Entry/exit semantics based on spread deviation
- Symmetric long/short handling on the spread
- Position neutrality (hedged legs)
- Execution timing assumptions
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Lookback window for spread statistics
- Entry/exit thresholds
- Maximum holding period (optional)
- Stop-loss on spread (optional)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a **market-neutral spread trading** strategy that exploits
mean reversion in the price relationship between two correlated assets.

The strategy:
- Constructs a spread from two assets with fixed hedge ratios
- Enters positions when the spread deviates significantly from its mean
- Exits when the spread reverts toward equilibrium
- Maintains neutral exposure by trading both legs simultaneously

Primary evaluation focuses on:
- correct construction of the spread
- correct handling of two-leg positions and signs
- state consistency and auditability
- absence of directional market exposure

---

## 2) Data Module
### 2.1 Inputs (Required)
Two synchronized OHLCV streams:

#### Asset A
- Frequency: same as Asset B
- Fields: `datetime, open, high, low, close, volume`

#### Asset B
- Frequency: same as Asset A
- Fields: `datetime, open, high, low, close, volume`

### 2.2 Alignment Rules (Frozen)
- Bars must be aligned by `datetime`.
- If either asset is missing data at time `t`, skip signal generation at `t`.
- No forward-filling across missing bars for spread computation.

---

## 3) Spread Construction (Frozen)
Let:
- `P_A_t` = close price of Asset A at time `t`
- `P_B_t` = close price of Asset B at time `t`
- `beta` = fixed hedge ratio (default `1.0`)

Define the spread:
- `spread_t = log(P_A_t) - beta * log(P_B_t)`

> The hedge ratio is fixed for the entire backtest to avoid look-ahead
> and implicit re-estimation bias.

---

## 4) Spread Statistics
### 4.1 Rolling Mean and Std (Frozen)
Using a rolling window of length `W`:

- `mu_t = mean(spread_{t-W+1 ... t})`
- `sigma_t = std(spread_{t-W+1 ... t})`

Define z-score:
- `z_t = (spread_t - mu_t) / sigma_t`

If `sigma_t == 0` or insufficient history:
- Do not generate signals.

---

## 5) Signal Module
Signals are evaluated at bar close.

### 5.1 Entry Signals (Frozen Logic)

**Enter Long Spread**
- Condition: `z_t <= -entry_z`
- Action:
  - Long Asset A
  - Short Asset B

**Enter Short Spread**
- Condition: `z_t >= entry_z`
- Action:
  - Short Asset A
  - Long Asset B

---

### 5.2 Exit Signals (Frozen Logic)

**Exit Spread Position**
- Condition: `abs(z_t) <= exit_z`

Optional exits:
- Maximum holding period exceeded
- Stop-loss on spread (see Section 7)

---

### 5.3 Signal Priority (Frozen)
On the same bar:
1) Stop-loss exit (if enabled)
2) Mean-reversion exit
3) Entry signal (only if flat)

---

## 6) Position & Portfolio Module
### 6.1 Position Mode (Frozen)
- Allowed states:
  - `Flat`
  - `LongSpread` (A long, B short)
  - `ShortSpread` (A short, B long)
- Only one spread position at a time.

### 6.2 Hedging Constraint (Frozen)
- Position sizes on both legs must respect:
  - `|notional_A| == |beta * notional_B|`
- No net directional exposure is allowed.

### 6.3 Sizing (Frozen Default)
- Fixed notional per spread trade.
- No pyramiding or scaling.

---

## 7) Risk Management
### 7.1 Optional Stop Loss (Tunable)
A stop-loss may be applied on the spread z-score:

- Long Spread: exit if `z_t <= -stop_z`
- Short Spread: exit if `z_t >= stop_z`

Default:
- Stop-loss disabled.

### 7.2 Optional Max Holding Period (Tunable)
- Exit if holding period exceeds `max_holding_bars`.

---

## 8) Execution Module (Frozen)
- Signals evaluated at bar close.
- Both legs executed at the same bar close.
- No partial fills; assume atomic execution for replay.
- Default: no slippage, no commission (unless harness applies them).

---

## 9) Edge Cases (Frozen)
- If one leg cannot be priced at `t`: no action.
- If sigma is zero or unstable: no signal.
- Do not reverse directly from long spread to short spread on the same bar; must pass through flat.

---

## 10) Required Outputs (Mandatory)

### 10.1 Trade Log (per completed spread trade)
Required fields:
- `trade_id`
- `asset_A`, `asset_B`
- `side` (`"long_spread"` / `"short_spread"`)
- `entry_time`, `exit_time`
- `entry_z`, `exit_z`
- `holding_bars`
- `pnl`, `pnl_pct`
- `reason_entry`
- `reason_exit`

### 10.2 Leg-Level Fill Log (Mandatory)
For each leg:
- `trade_id`
- `asset`
- `side` (`"long"` / `"short"`)
- `price`
- `notional`

### 10.3 Per-bar Audit Log (recommended)
At minimum:
- `datetime`
- `spread_t`, `mu_t`, `sigma_t`, `z_t`
- `position_state`
- `equity`

### 10.4 Summary Metrics
- total_return
- max_drawdown
- win_rate
- num_trades

---

## 11) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `W` (lookback window)
- `entry_z`, `exit_z`
- `stop_z` (if enabled)
- `max_holding_bars`

The model MUST NOT:
- re-estimate hedge ratio dynamically
- introduce additional indicators
- break leg neutrality
- use future data
