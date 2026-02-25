# Base Strategy Doc — Index Enhancement (Daily, Long-Only, Weight Tilt)
**Strategy ID:** index_enhancement_daily_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Strategy class: long-only index tracking with systematic weight tilts
- Universe selection rule based on constituent weights
- Momentum signal definition (5-day monotonic up/down)
- Weight adjustment semantics (base_ratio ± delta applied multiplicatively to index weights)
- Rebalancing schedule (daily evaluation and rebalance)
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Index constituent weight threshold for universe selection
- Base tracking ratio (`base_ratio`)
- Tilt magnitude (`delta`)
- Momentum window length (`mom_window`)
- Optional normalization method (cash handling / weight renormalization)
- Transaction cost assumptions (if enabled by harness)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement an **index enhancement** strategy that tracks a benchmark index while
systematically tilting weights toward "strong" constituents and away from "weak" constituents
based on a simple price momentum rule.

This benchmark tests whether a model can correctly implement:
- index-weighted portfolio construction
- daily signal computation and rebalance
- weight constraints and cash handling
- portfolio-level evaluation (excess return, tracking error, turnover)
- deterministic execution with complete audit logs

---

## 2) Data Module
### 2.1 Inputs (Required)
This strategy requires three aligned inputs:

#### A) Benchmark index price series
- Frequency: `1d`
- Fields: `datetime, open, high, low, close, volume` (volume may be absent for index; if absent, ignore)

#### B) Constituents daily OHLCV
- Frequency: `1d`
- Fields per constituent: `datetime, open, high, low, close, volume`

#### C) Dated constituent weights (index weights)
- Table fields:
  - `date` (trading date)
  - `symbol` (constituent identifier)
  - `weight` (index weight as fraction, e.g., 0.0123)
- The weight table must be defined at least on each rebalance date.

### 2.2 Alignment Rules (Frozen)
- Rebalance is performed on each trading date `D` using:
  - weights `w_i(D)` from the dated weight table (for date `D`)
  - momentum signal computed from **the last `mom_window` closes up to date `D`**
- If weights for date `D` are missing: skip rebalance on `D` (hold prior targets).

### 2.3 Universe Selection (Frozen)
On each rebalance date `D`, the tradable universe is:
- `U(D) = { i | w_i(D) >= weight_threshold }`

Only constituents in `U(D)` are eligible for holding.

---

## 3) Signal Module (Momentum Tilt)
### 3.1 Momentum Definition (Frozen)
Let `C_i[t]` be the close price series for constituent `i`.

Using the last `mom_window` closes ending at date `D`:
- `is_strong(i, D) = all(diff(C_i[D-mom_window+1 ... D]) > 0)`
- `is_weak(i, D)   = all(diff(C_i[D-mom_window+1 ... D]) < 0)`

If neither strong nor weak, the constituent is neutral.

If insufficient history for a constituent on date `D`, treat it as neutral (no tilt).

---

## 4) Portfolio Construction (Frozen Semantics)
### 4.1 Baseline Tracking Weight
Let:
- `base_ratio` be the baseline tracking ratio (default 0.8)
- `delta` be the tilt increment (default 0.2)

For each constituent `i ∈ U(D)` with index weight `w_i(D)`:

Define the **target weight multiplier** `m_i(D)`:
- If strong: `m_i(D) = base_ratio + delta`
- If weak:   `m_i(D) = base_ratio - delta`
- Else:      `m_i(D) = base_ratio`

Define the **raw target weight**:
- `raw_target_i(D) = w_i(D) * m_i(D)`

### 4.2 Normalization / Cash Handling (Frozen, but with allowed options)
Because `sum_i raw_target_i(D)` may differ from 1, the strategy must choose exactly one of:

**Option A (Default): Keep Cash**
- Set `target_i(D) = raw_target_i(D)`
- Remaining weight `1 - sum_i target_i(D)` is held as cash (uninvested)

**Option B (Optional): Renormalize to 100%**
- Set `target_i(D) = raw_target_i(D) / sum_j raw_target_j(D)` for all `i`
- No cash holding (fully invested)

The chosen option must be explicitly declared in outputs and must remain fixed throughout the run.

---

## 5) Rebalancing & Trading Rules
### 5.1 Rebalance Schedule (Frozen)
- Rebalance occurs on **every trading day** at bar close.

### 5.2 Long-Only Constraint (Frozen)
- No short selling is allowed.
- Target weights must satisfy: `target_i(D) >= 0`.

### 5.3 Holding Constraint (Frozen)
- Positions in constituents not in `U(D)` must be reduced to 0 target weight on date `D`.

### 5.4 Turnover (Frozen Reporting Requirement)
On each rebalance date `D`, compute portfolio turnover:
- `turnover(D) = 0.5 * sum_i |target_i(D) - target_i(D-1)|`

---

## 6) Execution Module (Frozen)
Backtest execution assumptions:
- Signals computed at **bar close** on date `D`.
- Orders executed at the **same bar close** (close-to-close rebalance).
- Default: no slippage, no commission (unless harness applies them).

---

## 7) Portfolio-Level Evaluation Outputs (Mandatory)
### 7.1 Daily Portfolio Return
Compute daily portfolio return using close-to-close returns and target weights.

### 7.2 Excess Return vs Benchmark (Mandatory)
- `excess_ret(D) = portfolio_ret(D) - benchmark_ret(D)`

### 7.3 Tracking Error (Mandatory)
Compute tracking error over a rolling window `TE_window` (default 252 trading days, tunable):
- `TE = std(excess_ret) * sqrt(annualization_factor)`

---

## 8) Edge Cases (Frozen)
- If a constituent has missing close for the rebalance date: set its target weight to 0 for that date.
- If benchmark close is missing: skip computing excess return for that date.
- If `base_ratio - delta < 0`, clamp at 0 (but defaults ensure non-negative).

---

## 9) Required Outputs (Mandatory)

### 9.1 Rebalance Log (per trading day)
Required fields:
- `date`
- `universe_size`
- `normalization_mode` (`"cash"` or `"renormalize"`)
- `base_ratio`, `delta`, `mom_window`, `weight_threshold`
- `sum_raw_target`
- `turnover`
- `num_strong`, `num_weak`, `num_neutral`

### 9.2 Holdings / Target Weights (per trading day)
For each `i ∈ U(D)`:
- `date`
- `symbol`
- `index_weight`
- `signal` (`"strong"|"weak"|"neutral"`)
- `target_weight`
- `raw_target_weight`

### 9.3 Equity Curve & Benchmark Curve
- daily portfolio value
- daily benchmark value

### 9.4 Summary Metrics
- total_return
- annualized_return
- max_drawdown
- average_excess_return
- tracking_error
- information_ratio (IR = mean(excess)/std(excess))
- average_turnover

---

## 10) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `weight_threshold`
- `base_ratio`, `delta`
- `mom_window`
- `normalization_mode` (cash vs renormalize, but must remain fixed across the run)
- `TE_window`

The model MUST NOT:
- introduce new alpha signals (no additional indicators/factors)
- alter the momentum definition (must remain monotonic 5-day up/down, unless mom_window is tuned)
- enable short selling
- use future data or future weights
