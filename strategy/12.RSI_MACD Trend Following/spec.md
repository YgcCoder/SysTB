# Base Strategy Doc — RSI / MACD Trend Following (Daily)
**Strategy ID:** rsi_macd_trend_daily_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Strategy class: single-asset trend following using ONE technical signal family
- Signal family must be either RSI-based OR MACD-based (exclusive)
- Entry/exit semantics and crossover/threshold logic
- Execution timing assumptions (bar close)
- Position mode (Long / Short / Flat) with reversal behavior
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- `signal_type`: choose `"RSI"` or `"MACD"` (must remain fixed for entire run)
- RSI periods and thresholds
- MACD periods (fast/slow/signal)
- Optional stop-loss percentage
- Transaction cost assumptions (if enabled by harness)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a classic **technical-indicator trend-following** strategy on daily bars.
The strategy uses exactly one of:
- RSI threshold/crossover rules, OR
- MACD DIF/DEA crossover rules

This benchmark tests:
- correct indicator computation and signal logic
- symmetric long/short handling and reversal execution
- deterministic, leakage-free implementation
- complete audit logging

---

## 2) Data Module
### 2.1 Inputs (Required)
Single asset OHLCV:
- Frequency: `1d`
- Fields: `datetime, open, high, low, close, volume`

### 2.2 Data Rules (Frozen)
- Bars must be sorted by datetime ascending.
- If insufficient history for indicator computation: no signal.

---

## 3) Indicator Module
Only one signal family is active. The selected family is controlled by `signal_type`.

---

### 3.1 RSI (if `signal_type="RSI"`) — Frozen definitions
Compute RSI on close using period `rsi_period`:

- `RSI_t = RSI(close, rsi_period)`

Signal thresholds:
- `rsi_upper` (default 70)
- `rsi_lower` (default 30)

---

### 3.2 MACD (if `signal_type="MACD"`) — Frozen definitions
Compute MACD on close with:
- fast EMA period `macd_fast` (default 12)
- slow EMA period `macd_slow` (default 26)
- signal EMA period `macd_signal` (default 9)

Definitions:
- `DIF_t = EMA(close, macd_fast) - EMA(close, macd_slow)`
- `DEA_t = EMA(DIF, macd_signal)`

---

## 4) Signal Module (Exclusive Mode)
Signals are evaluated at bar close.

### 4.1 RSI Trend Rules (Frozen, if RSI mode)
Use threshold cross semantics:

**Enter Long**
- Condition: `RSI_t >= rsi_upper` AND `RSI_{t-1} < rsi_upper`

**Enter Short**
- Condition: `RSI_t <= rsi_lower` AND `RSI_{t-1} > rsi_lower`

**Exit Policy (Frozen)**
- Reversal-only: a long exits only when a valid short entry triggers, and vice versa.
- No neutral exit.

---

### 4.2 MACD Trend Rules (Frozen, if MACD mode)
Use DIF/DEA crossover semantics:

**Enter Long (Golden Cross)**
- Condition: `DIF_t > DEA_t` AND `DIF_{t-1} <= DEA_{t-1}`

**Enter Short (Death Cross)**
- Condition: `DIF_t < DEA_t` AND `DIF_{t-1} >= DEA_{t-1}`

**Exit Policy (Frozen)**
- Reversal-only: a long exits only when a valid short entry triggers, and vice versa.

---

### 4.3 Signal Priority (Frozen)
On the same bar:
1) Stop-loss exit (if enabled and triggered)
2) Reversal entry (close opposite then enter)
3) Otherwise hold

No simultaneous long and short positions are allowed.

---

## 5) Position & Portfolio Module
### 5.1 Position Mode (Frozen)
- Allowed states: `Long`, `Short`, `Flat`
- At most one active position per instrument.

### 5.2 Sizing (Frozen Default)
- Single-instrument sizing: 100% of allocated capital (all-in / all-out).
- No pyramiding, no partial scaling.

---

## 6) Risk Management
### 6.1 Optional Stop Loss (Tunable)
A symmetric percentage stop-loss may be enabled:

- For Long: exit if `close_t <= entry_price * (1 - stop_loss_pct)`
- For Short: exit if `close_t >= entry_price * (1 + stop_loss_pct)`

Default:
- `stop_loss_pct = null` (disabled)

Stop-loss exits at bar close.

---

## 7) Execution Module (Frozen)
- Signals evaluated at bar close.
- Orders executed at the same bar close.
- Default: no slippage, no commission (unless harness applies them).

---

## 8) Edge Cases (Frozen)
- If indicator values are undefined on date `D`: no signal.
- If both RSI and MACD parameters are provided, only the chosen `signal_type` is used.
- Tie/flat cases (equalities) follow the strict inequalities in the rule definitions.

---

## 9) Required Outputs (Mandatory)

### 9.1 Trade Log (per completed trade)
Required fields:
- `trade_id`
- `instrument`
- `signal_type` (`"RSI"` or `"MACD"`)
- `entry_time`, `entry_price`
- `exit_time`, `exit_price`
- `side` (`"long"` or `"short"`)
- `pnl`, `pnl_pct`
- `reason_entry` (e.g., `"rsi_upper_cross"`, `"rsi_lower_cross"`, `"macd_golden_cross"`, `"macd_death_cross"`)
- `reason_exit` (`"reversal"` or `"stop_loss"`)

### 9.2 Per-bar Audit Log (recommended)
At minimum:
- `datetime`, `close`
- if RSI: `RSI_t`, `signal`
- if MACD: `DIF_t`, `DEA_t`, `signal`
- `position_state`
- `equity`

### 9.3 Summary Metrics
- total_return
- annualized_return
- max_drawdown
- win_rate
- num_trades

---

## 10) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `signal_type` (RSI vs MACD, but must be fixed for the full run once chosen)
- RSI parameters: `rsi_period`, `rsi_upper`, `rsi_lower`
- MACD parameters: `macd_fast`, `macd_slow`, `macd_signal`
- `stop_loss_pct`

Constraints:
- RSI: `rsi_lower < rsi_upper`
- MACD: `macd_fast < macd_slow`

The model MUST NOT:
- combine RSI and MACD signals simultaneously
- introduce new indicators
- use future data
- introduce pyramiding
