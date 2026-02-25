# Base Strategy Doc — Volatility Targeting / Vol Scaling (Daily)
**Strategy ID:** vol_targeting_daily_v1  
**Version:** 1.0  
**Document Type:** Model-Facing Strategy Specification (SysTradeBench)

---

## 0) Modification Policy (Strict)
This document defines **frozen strategy semantics** and **tunable parameters**.

### Frozen (MUST NOT change)
- Strategy class: single-asset volatility targeting (risk scaling)
- Volatility estimator based on trailing returns
- Target volatility control rule (linear scaling with cap)
- Long-only exposure with explicit cash allocation
- Rebalancing frequency and execution timing
- Output requirements and audit fields

### Tunable (MAY change within bounds)
- Volatility lookback window `L_vol`
- Target volatility level `target_vol`
- Maximum leverage / exposure cap `max_exposure`
- Volatility estimator type (std of returns vs EWMA), if explicitly allowed
- Annualization factor (fixed by market calendar if provided by harness)

If any conflict exists, **Frozen** rules override.

---

## 1) Strategy Objective
Implement a **volatility targeting** strategy that dynamically scales exposure to a single
risky asset in order to maintain a stable ex-ante portfolio volatility.

The strategy:
- estimates realized volatility from trailing returns
- scales exposure proportionally to the ratio of target volatility to realized volatility
- caps exposure to avoid excessive leverage
- allocates residual capital to cash

This benchmark tests:
- correct volatility estimation and annualization
- stable, deterministic risk scaling
- correct handling of edge cases (near-zero volatility)
- portfolio-level logging and auditability

---

## 2) Data Module
### 2.1 Inputs (Required)
Single asset OHLCV:

- Frequency: `1d`
- Fields:
  - `datetime`, `open`, `high`, `low`, `close`, `volume`

A cash return series is optional; if absent, cash return is assumed 0.

### 2.2 Alignment Rules (Frozen)
- Data must be sorted by `datetime`.
- If insufficient history for volatility estimation on date `D`, do not rebalance on `D`
  (hold previous target exposure).

---

## 3) Return & Volatility Estimation
### 3.1 Daily Returns (Frozen)
Let:
- `C[D]` be the close price on date `D`.

Compute daily return:
- `r[D] = C[D] / C[D-1] - 1`

If `C[D-1]` is unavailable:
- return is undefined; skip volatility update on `D`.

---

### 3.2 Realized Volatility (Frozen)
Using a trailing window of length `L_vol`:

- `sigma_daily(D) = std( r[D-L_vol+1 ... D] )`

Annualized volatility:
- `sigma_ann(D) = sigma_daily(D) * sqrt(annualization_factor)`

Default `annualization_factor = 252`.

If `sigma_daily(D) == 0` or insufficient history:
- do not update exposure on `D`.

---

## 4) Exposure Scaling Rule (Frozen)
### 4.1 Raw Target Exposure
Define:
- `target_vol` = desired annualized volatility

Compute raw exposure:
- `raw_exposure(D) = target_vol / sigma_ann(D)`

---

### 4.2 Exposure Cap (Frozen)
Apply a hard cap:
- `exposure(D) = min( raw_exposure(D), max_exposure )`

Exposure represents the fraction of portfolio allocated to the risky asset.

---

### 4.3 Cash Allocation (Frozen)
- Risky asset weight: `w_asset(D) = exposure(D)`
- Cash weight: `w_cash(D) = 1 - w_asset(D)`

Constraints:
- `0 <= w_asset(D) <= max_exposure`
- `w_cash(D) >= 0`

No leverage beyond `max_exposure` is allowed.

---

## 5) Rebalancing & Execution
### 5.1 Rebalance Frequency (Frozen)
- Rebalance occurs on **every trading day** at bar close, subject to data availability.

### 5.2 Execution Assumptions (Frozen)
- Signals computed at **bar close**.
- Orders executed at the **same bar close** (close-to-close).
- Default: no slippage, no commission (unless harness applies them).

### 5.3 Turnover (Mandatory Reporting)
- `turnover(D) = |w_asset(D) - w_asset(D-1)|`

---

## 6) Risk & Safety Constraints (Frozen)
- Long-only exposure to the risky asset.
- No short selling.
- No leverage beyond `max_exposure`.
- No look-ahead in volatility estimation.

---

## 7) Edge Cases (Frozen)
- If `sigma_ann(D)` is extremely small (below numerical threshold), treat as invalid and
  hold previous exposure.
- If missing returns within the volatility window, exclude those days; if too many are
  missing, skip rebalance.
- Exposure updates must be deterministic given identical inputs.

---

## 8) Required Outputs (Mandatory)

### 8.1 Rebalance Log (per trading day)
Required fields:
- `date`
- `L_vol`
- `target_vol`
- `max_exposure`
- `sigma_daily`
- `sigma_ann`
- `raw_exposure`
- `final_exposure`
- `turnover`

### 8.2 Target Weights (per trading day)
- `date`
- `asset_weight`
- `cash_weight`

### 8.3 Equity Curve
- daily portfolio value

### 8.4 Summary Metrics
- total_return
- annualized_return
- realized_volatility
- volatility_error (|realized_vol - target_vol|)
- max_drawdown
- average_turnover

---

## 9) Allowed Optimization Scope (Tunable)
The model MAY propose changes to:
- `L_vol`
- `target_vol`
- `max_exposure`
- volatility estimator type (if allowed by the harness configuration)

The model MUST NOT:
- introduce directional alpha signals
- use future data
- enable shorting or uncapped leverage
