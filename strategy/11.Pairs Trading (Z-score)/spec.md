# Base Strategy Doc — Pairs Trading (Z-score, Mean Reversion)
**Strategy ID:** pairs_trading_zscore_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Strategy class: two-asset pairs trading with fixed hedge ratio
- Spread construction and z-score normalization
- Mean-reversion entry/exit semantics
- Symmetric long/short handling on the pair
- Market-neutral constraint (hedged legs)
- Execution timing assumptions
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Rolling window length `W`
- Entry/exit z-score thresholds
- Stop-loss threshold on z-score (optional)
- Maximum holding period (optional)
- Hedge ratio value `beta` (fixed for entire run, if enabled by harness)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a **pairs trading** strategy that exploits mean reversion in the
relative pricing of two correlated assets.

The strategy:
- constructs a normalized spread using a fixed hedge ratio
- computes a rolling z-score of the spread
- enters positions when deviations are large
- exits when the spread reverts toward equilibrium
- maintains market-neutral exposure by trading both legs simultaneously

Primary evaluation focuses on:
- correct spread construction and normalization
- correct sign conventions for both legs
- deterministic state management and auditability
- absence of directional market exposure

---

## 2) Data Module
### 2.1 Inputs (Required)
Two synchronized OHLCV streams:

#### Asset X
- Frequency: aligned with Asset Y
- Fields: `datetime, open, high, low, close, volume`

#### Asset Y
- Frequency: aligned with Asset X
- Fields: `datetime, open, high, low, close, volume`

### 2.2 Alignment Rules (Frozen)
- Bars must align on `datetime`.
- If either asset is missing data at time `t`, skip signal generation at `t`.
- No forward-filling across missing bars for spread computation.

---

## 3) Spread Construction (Frozen)
Let:
- `P_X_t` = close price of Asset X at time `t`
- `P_Y_t` = close price of Asset Y at time `t`
- `beta`  = fixed hedge ratio (default `1.0`)

Define the spread:
- `spread_t = log(P_X_t) - beta * log(P_Y_t)`

> The hedge ratio is fixed for the entire run to ensure reproducibility
> and to avoid look-ahead or implicit re-estimation bias.

---

## 4) Spread Statistics (Frozen)
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

**Enter Long Pair**
- Condition: `z_t <= -entry_z`
- Action:
  - Long Asset X
  - Short Asset Y

**Enter Short Pair**
- Condition: `z_t >= entry_z`
- Action:
  - Short Asset X
  - Long Asset Y

---

### 5.2 Exit Signals (Frozen Logic)

**Exit Pair Position**
- Condition: `abs(z_t) <= exit_z`

Optional exits:
- Stop-loss on z-score (Section 7.1)
- Maximum holding period (Section 7.2)

---

### 5.3 Signal Priority (Frozen)
On the same bar:
1) Stop-loss exit (if enabled)
2) Mean-reversion exit
3) Entry signal (only if flat)

No direct reversal on the same bar; must pass through flat.

---

## 6) Position & Portfolio Module
### 6.1 Position Mode (Frozen)
- Allowed states:
  - `Flat`
  - `LongPair`  (X long, Y short)
  - `ShortPair` (X short, Y long)
- Only one pair position at a time.

### 6.2 Hedging Constraint (Frozen)
- Notional neutrality:
  - `|notional_X| == |beta * notional_Y|`
- No net directional exposure is allowed.

### 6.3 Sizing (Frozen Default)
- Fixed notional per pair trade.
- No pyramiding or scaling.

---

## 7) Risk Management
### 7.1 Optional Stop Loss (Tunable)
A stop-loss may be applied on the z-score:

- If in `LongPair`: exit if `z_t <= -stop_z`
- If in `ShortPair`: exit if `z_t >= stop_z`

Default:
- Stop-loss disabled.

### 7.2 Optional Max Holding Period (Tunable)
- Exit if holding period exceeds `max_holding_bars`.

---

## 8) Execution Module (Frozen)
- Signals evaluated at bar close.
- Both legs executed at the same bar close.
- Atomic execution assumed for replay (no partial fills).
- Default: no slippage, no commission (unless harness applies them).

---

## 9) Edge Cases (Frozen)
- If either asset is missing at `t`: no action.
- If sigma is zero or unstable: no signal.
- Do not enter if already in a pair position.
- Must exit before switching direction.

---

## 10) Required Outputs (Mandatory)

### 10.1 Trade Log (per completed pair trade)
Required fields:
- `trade_id`
- `asset_X`, `asset_Y`
- `side` (`"long_pair"` / `"short_pair"`)
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
- `W`
- `entry_z`, `exit_z`
- `stop_z` (if enabled)
- `max_holding_bars`
- `beta` (only if declared upfront and fixed for the entire run)

The model MUST NOT:
- dynamically re-estimate hedge ratios
- introduce additional indicators
- break notional neutrality
- use future data
