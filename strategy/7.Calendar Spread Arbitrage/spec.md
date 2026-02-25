# Base Strategy Doc — Calendar Spread Arbitrage (Mean-Reversion, Replay-Friendly)
**Strategy ID:** calendar_spread_basic_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Strategy class: two-contract calendar spread (same underlying, different maturities)
- Spread definition (near vs far) and mean-reversion trading logic
- Symmetric long/short handling on the spread
- Hedged two-leg execution (market-neutral)
- Execution timing assumptions
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Rolling window for spread statistics `W`
- Entry/exit thresholds (in std units or z-score)
- Stop-loss threshold
- Maximum holding period (optional)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a **calendar spread arbitrage** strategy that trades the mean reversion of the
price spread between two contracts of the **same underlying** but different expiries.

The strategy:
- Defines a spread between the near-month and far-month contracts
- Enters when the spread deviates from its rolling mean
- Exits when the spread reverts toward the mean
- Maintains hedged exposure by trading both legs simultaneously

Primary evaluation focuses on:
- correct two-leg sign conventions (near vs far)
- correct state management and neutrality
- deterministic replay execution and complete audit logs
- no look-ahead

---

## 2) Data Module
### 2.1 Inputs (Required)
Two synchronized OHLCV streams:

#### Near Contract (N)
- Frequency: aligned with Far
- Fields: `datetime, open, high, low, close, volume`

#### Far Contract (F)
- Frequency: aligned with Near
- Fields: `datetime, open, high, low, close, volume`

### 2.2 Alignment Rules (Frozen)
- Bars must align on `datetime`.
- If either contract is missing data at time `t`, skip signal generation at `t`.
- No forward-filling across missing bars for spread computation.

### 2.3 Contract Identity (Frozen)
- Both legs must represent the **same underlying** with different maturities.
- For reproducible backtests, the benchmark may provide:
  - (a) explicit near/far series, OR
  - (b) synthetic near/far proxies (if true expiries are unavailable)

The strategy logic is identical in either case.

---

## 3) Spread Construction (Frozen)
Let:
- `P_N_t` = close price of Near contract at time `t`
- `P_F_t` = close price of Far contract at time `t`

Define the calendar spread:
- `spread_t = P_N_t - P_F_t`

(Absolute spread; alternative log-spread is NOT allowed in this frozen version.)

---

## 4) Spread Statistics (Rolling) (Frozen)
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
Interpretation: if spread is high, near is expensive vs far; expect reversion.

**Enter Short Spread**
- Condition: `z_t >= entry_z`
- Action:
  - Short Near contract (N)
  - Long Far contract (F)

**Enter Long Spread**
- Condition: `z_t <= -entry_z`
- Action:
  - Long Near contract (N)
  - Short Far contract (F)

---

### 5.2 Exit Signals (Frozen Logic)
**Exit Spread Position**
- Condition: `abs(z_t) <= exit_z`

Optional exits:
- Stop-loss (Section 7.1)
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
  - `LongSpread`  (Long Near, Short Far)
  - `ShortSpread` (Short Near, Long Far)
- Only one calendar spread position at a time.

### 6.2 Hedging Constraint (Frozen)
- Trade both legs simultaneously with equal absolute notional:
  - `|notional_N| == |notional_F|`
- No net directional exposure to the underlying is allowed.

### 6.3 Sizing (Frozen Default)
- Fixed notional per spread trade.
- No pyramiding or scaling.

---

## 7) Risk Management
### 7.1 Optional Stop Loss (Tunable)
A stop-loss may be applied on z-score:

- If in `LongSpread`: exit if `z_t <= -stop_z`
- If in `ShortSpread`: exit if `z_t >= stop_z`

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
- If either leg missing at `t`: no action.
- If sigma is zero or undefined: no signal.
- Do not enter if already in a spread position.
- Must exit before switching direction.

---

## 10) Required Outputs (Mandatory)

### 10.1 Trade Log (per completed spread trade)
Required fields:
- `trade_id`
- `near_contract`, `far_contract`
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
- `contract`
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

The model MUST NOT:
- change the spread definition (must remain `P_N - P_F`)
- use dynamic hedge ratios
- break notional neutrality
- use future data
- add new indicators
