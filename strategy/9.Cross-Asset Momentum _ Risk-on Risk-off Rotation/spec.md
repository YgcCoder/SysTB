# Base Strategy Doc — Cross-Asset Momentum / Risk-on Risk-off Rotation (Daily)
**Strategy ID:** cross_asset_momentum_roro_daily_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Strategy class: cross-asset rotation based on time-series momentum
- Momentum signal definition (lookback return sign)
- Decision set: allocate to exactly one asset (winner-takes-all) or to cash
- Rebalancing frequency and execution timing
- Long-only portfolio (no shorting)
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Lookback window length `L`
- Asset universe composition (must be chosen from benchmark-provided list)
- Minimum edge threshold `min_return_threshold` (optional)
- Cash handling (explicit)
- Transaction costs (if enabled by harness)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a simple **risk-on / risk-off** rotation strategy using **time-series momentum**
across a small set of broad assets (e.g., equity vs bonds).

At each rebalance date, the strategy:
- computes a momentum score per asset from trailing returns
- selects a single asset to hold (100% weight) if momentum is sufficiently positive
- otherwise holds cash (or a designated defensive asset if configured)

This benchmark tests:
- multi-asset data handling and rebalance mechanics
- signal correctness and determinism
- clean portfolio construction with explicit cash handling
- out-of-sample stability and turnover behavior

---

## 2) Data Module
### 2.1 Inputs (Required)
A set of `K` assets, each with daily OHLCV:

- Frequency: `1d`
- Fields per asset:
  - `datetime`, `open`, `high`, `low`, `close`, `volume`

A cash series is optional; if no cash return series is provided, cash return is assumed 0.

### 2.2 Alignment Rules (Frozen)
- All assets must be aligned by `datetime`.
- If any asset is missing data on date `D`, that asset is excluded from scoring on `D`.
- If fewer than `min_assets_required` assets are available, hold cash.

---

## 3) Signal Module (Time-Series Momentum)
### 3.1 Momentum Score (Frozen)
Let `C_i[D]` be the close price for asset `i` on date `D`.
Lookback window `L` trading days.

Trailing return:
- `ret_i(D) = C_i[D] / C_i[D-L] - 1`

Momentum score:
- `score_i(D) = ret_i(D)`  (raw return score)

If `C_i[D-L]` is unavailable: asset `i` is not scored on date `D`.

---

## 4) Selection & Allocation Rules
### 4.1 Winner Selection (Frozen)
On each rebalance date `D`:
1) Compute `score_i(D)` for all available assets.
2) Let `i* = argmax_i score_i(D)`.

### 4.2 Risk-on / Risk-off Decision (Frozen)
Default policy:

- If `score_{i*}(D) >= min_return_threshold`:
  - Allocate 100% to asset `i*`
- Else:
  - Allocate 100% to cash

Where `min_return_threshold` default is `0.0`.

Optional defensive variant (allowed, but must be fixed):
- If threshold not met, allocate 100% to a designated defensive asset `defensive_asset`
  (must be a member of the asset universe, e.g., TLT).

The chosen policy must remain fixed across the run and must be declared in outputs.

---

## 5) Portfolio Construction (Frozen)
### 5.1 Target Weights
Winner-takes-all target weights:
- `w_{i*}(D) = 1.0`
- `w_j(D) = 0.0` for all `j != i*`

Cash mode:
- If risk-off triggers, all asset weights are 0 and cash weight is 1.

### 5.2 Long-only Constraints
- All weights must be non-negative.
- No leverage.

---

## 6) Rebalancing & Execution
### 6.1 Rebalance Frequency (Frozen)
- Rebalance occurs on **every trading day** at bar close.

### 6.2 Execution Assumptions (Frozen)
- Signals computed at **bar close**.
- Orders executed at the **same bar close** (close-to-close).
- Default: no slippage, no commission (unless harness applies them).

### 6.3 Turnover (Mandatory Reporting)
- `turnover(D) = 0.5 * sum_i |w_i(D) - w_i(D-1)|`
(Cash is included as an implicit component.)

---

## 7) Edge Cases (Frozen)
- If multiple assets tie for max score: pick the one with lexicographically smallest symbol (deterministic tie-break).
- If `L` lookback not available for all assets on date `D`: score only those with enough history.
- If fewer than `min_assets_required` assets are scorable: risk-off (cash or defensive asset).

---

## 8) Required Outputs (Mandatory)

### 8.1 Rebalance Log (per trading day)
Required fields:
- `date`
- `L`
- `min_return_threshold`
- `risk_off_policy` (`"cash"` or `"defensive_asset"`)
- `defensive_asset` (null if cash)
- `selected_asset` (null if cash and no defensive asset)
- `selected_score`
- `turnover`
- `num_assets_scored`

### 8.2 Target Weights (per trading day)
For each asset in universe:
- `date`
- `symbol`
- `score`
- `target_weight`

### 8.3 Equity Curve
- daily portfolio value

### 8.4 Summary Metrics
- total_return
- annualized_return
- max_drawdown
- win_rate (optional for portfolio; if defined, use daily sign correctness)
- num_rebalances
- average_turnover

---

## 9) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `L`
- `min_return_threshold`
- `risk_off_policy` (cash vs defensive asset; must remain fixed once chosen)
- `defensive_asset` (if policy uses defensive asset; must be in universe)

The model MUST NOT:
- introduce shorting or leverage
- use additional indicators beyond trailing return
- use future data
