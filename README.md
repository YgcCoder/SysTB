# SysTradeBench (SysTB)


**SysTradeBench** is the first benchmark to apply an iterative build–test–patch protocol with frozen-semantics constraints and drift-aware diagnostics for evaluating LLMs on full strategy-to-code generation in quantitative trading, featuring sandboxed execution, validity gates, and a cross-model arena.

> *SysTradeBench: An Iterative Build–Test–Patch Benchmark for Strategy-to-Code Trading Systems with Drift-Aware Diagnostics.* **KDD 2026.**

---

## Highlights

- **12 real-world trading strategies** across US equities, A-shares, and crypto — each with a frozen natural-language spec and semantic schema
- **17 frontier LLMs evaluated** (GPT-5, o3, Claude Opus/Sonnet, Gemini 3, Grok 4, DeepSeek-V3, GLM-4, Qwen3-Coder, ...) — 20 invited, 3 excluded due to API failure
- **4-dimension scorecard** (D1 Spec Fidelity · D2 Risk Discipline · D3 Reliability · D4 OOS Robustness) with automatic validity gates
- **Iterative refinement protocol** — Iter0 zero-shot → Iter1–3 evidence-driven patching with frozen semantics
- **N×N cross-evaluation arena** — every reviewer model scores every submitter; self-reviews excluded

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Add your API keys
cp configs/models.yaml.template configs/models.yaml
# Edit configs/models.yaml

# 3. Run Iter0 (zero-shot) — one model, one strategy
python scripts/run_experiment.py --config-dir configs --iter 0 \
  --models gpt_5_2 --strategies bollinger_mean_reversion

# 4. Run the full pipeline (all models × 12 strategies)
python scripts/run_experiment.py --config-dir configs --iter 0
```

---

## Full Iterative Pipeline

The benchmark runs in four sequential phases. Each phase produces artifacts consumed by the next.

### Step 1 — Iter0: Zero-Shot Generation

All models generate strategy code from the frozen spec with no prior feedback.

```bash
# Run all 17 models × 12 strategies
python scripts/run_experiment.py --config-dir configs --iter 0

# Or target a specific model / strategy
python scripts/run_experiment.py --config-dir configs --iter 0 \
  --models gpt_5_2 o3 --strategies bollinger_mean_reversion
```

**Output per submission** → `results/iter0_submissions/{model}/{strategy}/`
```
generation/          ← raw LLM response
submission/
  strategy_card.json ← structured strategy interpretation
  strategy.py        ← executable trading code
  trade_log.csv      ← per-trade events
  audit_log.csv      ← per-bar diagnostics
reports/
  scorecard.json     ← D1–D4 scores + gate results
```

---

### Step 2 — Arena: N×N Cross-Evaluation

Every reviewer model scores every submitter's `strategy_card.json` + `strategy.py` on D1 (Spec Fidelity) and D2 (Risk Discipline). Self-reviews are recorded but excluded from rankings.

```bash
# Evaluate one strategy (run once per strategy)
python scripts/cross_evaluation.py \
  --strategy bollinger_mean_reversion \
  --config-dir configs \
  --results-dir results \
  --iter 0
```

**Output** → `results/iter0_submissions/{model}/{strategy}/cross_evaluations.json`  
**Report** → `results/bollinger_mean_reversion_iter0_cross_evaluation.md`

---

### Step 3 — Select Top Models for Refinement

Aggregates peer scores from Step 2, picks the best model per provider (to avoid vendor monopoly), and writes the shortlist for Iter1/2.

```bash
python scripts/select_top_models.py \
  --strategy bollinger_mean_reversion \
  --results-dir results \
  --top-n 5
```

**Output** → `results/iter1_iter2_models.yaml` (consumed automatically by Step 4)

---

### Step 4 — Iter1 & Iter2: Evidence-Driven Refinement

Top-5 providers receive their Iter0 evidence bundle (scorecard, gate failures, peer reviews) and submit constrained patches (≤ 50 changed lines, frozen semantics).

```bash
# Iter 1: first refinement round
python scripts/run_experiment.py --config-dir configs --iter 1

# Iter 2: second refinement round
python scripts/run_experiment.py --config-dir configs --iter 2
```

Each iteration automatically loads `results/iter1_iter2_models.yaml` to know which models to run. The evidence bundle from the previous iteration is included in the prompt.

> **Convergence note**: By Iter2, top models reach 95.4% code similarity. Iter3 uses multi-objective feedback (`D1–D3 ≥ 0.85` + `Sharpe ≥ 1.5`) to break the convergence trap — see Figure 2 in Results.

---

### Directory Layout After Full Run

```
results/
├── iter0_submissions/{model}/{strategy}/   ← Iter0 artifacts
│   ├── generation/
│   ├── submission/  (strategy_card.json, strategy.py, *.csv)
│   ├── reports/     (scorecard.json)
│   └── cross_evaluations.json
├── iter1_iter2_models.yaml                 ← top-5 shortlist
├── iter1_submissions/…                     ← Iter1 artifacts (same layout)
├── iter2_submissions/…                     ← Iter2 artifacts
└── arena/
    ├── cross_eval_ranking.csv
    └── validity_gates.csv
```

---

## Framework

### System Architecture and Iterative Workflow

<img src="docs/figures/figure1_architecture.png" width="720" alt="SysTB Architecture">

Three-layer pipeline with iterative execution control: **Input Layer** (frozen spec + OHLCV data + evidence bundle) → **Model Generation Layer** (strategy card + code + audit logs) → **Evaluation Layer** (D1–D4 scorecards + arena). The Executor enforces validity gates, detects semantic drift, and feeds the next evidence bundle.

### Validity Gates

`Parse → Schema → Exec → Determ → Anti-Leak → Audit`

Any gate failure short-circuits evaluation; Iter k results are invalidated on semantic drift.

### Iterations

| | Description | Models | Constraint |
|---|---|---|---|
| **Iter0** | Zero-shot generation | 17 models | None |
| **Iter1–3** | Evidence-driven patching | Top-5 providers | ≤50 changed lines, frozen semantics |

---

## Strategy Library

12 classic quantitative strategies spanning trend-following, mean-reversion, arbitrage, and risk management:

| # | Strategy | Markets |
|---|----------|---------|
| 1 | Bollinger Band Mean Reversion | US · CN · Crypto |
| 2 | Double Moving Average Crossover | US · CN · Crypto |
| 3 | Turtle / Donchian Breakout | US · CN · Crypto |
| 4 | Dual Thrust | Crypto |
| 5 | R-Breaker | Crypto |
| 6 | Spread Trading | US · CN |
| 7 | Calendar Spread Arbitrage | US |
| 8 | Index Enhancement | US · CN |
| 9 | Cross-Asset Momentum / Risk-on Risk-off Rotation | US · CN |
| 10 | Volatility Targeting / Vol Scaling | US · CN · Crypto |
| 11 | Pairs Trading (Z-score) | US · CN |
| 12 | RSI / MACD Trend Following | US · CN · Crypto |

Each strategy includes `spec.md` (frozen natural-language specification) and `spec.json` (semantic schema for D1 evaluation).

---

## Results

### RQ1.1 — Validity Gate Pass Rates (Table 3)

17 models × 12 strategies × 6 gates (3 models excluded due to API failure). Top-4 models achieve ≥ 91.7% across all gates; lower-tier models show cascading failures (parse succeeds but downstream gates fail).

| Model | Strategies | Parse | Schema | Exec | Determ | Anti-Leak | Audit |
|-------|-----------|-------|--------|------|--------|-----------|-------|
| GPT-5.2 | 12/12 | 100% | 100% | 100% | 100% | 100% | 100% |
| GPT-5.1 | 12/12 | 100% | 100% | 100% | 100% | 100% | 100% |
| o3 | 12/12 | 100% | 100% | 100% | 100% | 100% | 100% |
| Grok-4 Fast | 12/12 | 100% | 100% | 100% | 100% | 100% | 91.7% |
| GLM-4.6 | 12/12 | 100% | 100% | 91.7% | 91.7% | 100% | 91.7% |
| DeepSeek-V3 | 12/12 | 100% | 100% | 91.7% | 91.7% | 100% | 91.7% |
| Grok-4.1 FR | 11/12 | 91.7% | 91.7% | 91.7% | 91.7% | 91.7% | 83.3% |
| Grok-3 | 12/12 | 100% | 100% | 83.3% | 83.3% | 100% | 83.3% |
| Grok-Code Fast | 12/12 | 100% | 100% | 83.3% | 83.3% | 100% | 83.3% |
| Claude Sonnet | 12/12 | 100% | 91.7% | 91.7% | 91.7% | 91.7% | 83.3% |
| Claude Opus | 12/12 | 100% | 91.7% | 83.3% | 83.3% | 83.3% | 75.0% |
| Gemini-3 Pro | 12/12 | 100% | 83.3% | 75.0% | 75.0% | 83.3% | 66.7% |
| GLM-4.7 | 7/12 | 58.3% | 58.3% | 58.3% | 58.3% | 58.3% | 50.0% |
| Grok-4 | 3/12 | 25.0% | 25.0% | 25.0% | 25.0% | 25.0% | 25.0% |
| Gemini-3 Flash | 6/12 | 50.0% | 41.7% | 41.7% | 41.7% | 41.7% | 33.3% |
| Gemini-2.5 Pro | 12/12 | 100% | 66.7% | 50.0% | 41.7% | 50.0% | 33.3% |
| DeepSeek-R1 | 1/12 | 8.3% | 8.3% | 8.3% | 8.3% | 8.3% | 8.3% |

**Key finding**: 16.6pp gap between parse success (78.4%) and full-gate pass (61.8%) — many models produce syntactically valid but functionally broken code. Raw data: [`results/arena/validity_gates.csv`](results/arena/validity_gates.csv).

---

### RQ1.2 — Quality Scoring by Strategy (Table 4)

Strategy complexity strongly predicts quality (Spearman ρ = −0.68, p < 0.05):

| Strategy | LLM Score | QR Score | Overall | Valid |
|----------|-----------|----------|---------|-------|
| Double MA Crossover | 8.2 | 7.5 | **7.85** | 17/20 |
| Bollinger Mean Reversion | 7.8 | 7.1 | **7.45** | 16/20 |
| RSI/MACD Trend | 7.5 | 6.9 | **7.20** | 15/20 |
| Volatility Targeting | 7.3 | 6.8 | **7.05** | 14/20 |
| Spread Trading | 7.1 | 6.5 | **6.80** | 13/20 |
| Dual Thrust | 6.8 | 6.2 | **6.50** | 12/20 |
| Cross-Asset Momentum | 6.5 | 6.0 | **6.25** | 11/20 |
| Turtle/Donchian | 6.3 | 5.8 | **6.05** | 10/20 |
| Pairs Trading (Z-score) | 5.8 | 5.3 | **5.55** | 8/20 |
| Calendar Spread | 5.5 | 5.0 | **5.25** | 7/20 |
| R-Breaker | 6.0 | 5.5 | **5.75** | 9/20 |
| Index Enhancement | 5.2 | 4.8 | **5.00** | 6/20 |

LLM peer-review scores (avg 6.7) exceed QR automated scores (avg 6.1) by 0.6 pts — cross-evaluators tend to overlook subtle reliability issues.

---

### RQ2 — OOS Execution Robustness

Among 235 sampled OOS tests: **217 (92.3%) execute successfully**, 18 (7.7%) encounter runtime failures (KeyError, TypeError). 10 out of 17 models achieve 100% OOS success. Failures concentrate in Calendar Spread (`int(dict)` bugs) and Turtle/Donchian (`KeyError: 'L_entry'`) — shallow 1–2 line bugs that pass static gates but fail at runtime.

---

### Figure 2 — RQ3: Evidence-Driven Repair Trajectories

<img src="docs/figures/figure2_learning_curves.png" width="680" alt="Learning Curves">

Learning curves for 3 top models (GPT-5.2, o3, Grok-4 Fast) across 4 iterations on Bollinger Mean Reversion:
- **Iter0→Iter1**: largest quality jump (+0.42 avg), dominated by D4 (+0.70) and D3 (+0.25) gains
- **Iter2**: convergence trap — 95.4% code similarity, OOS return drops to −4.6%
- **Iter3**: multi-objective recovery (+22.2% OOS return) by adding explicit Sharpe/return targets

---

### Figure 3 — RQ4: Token Usage and Cost-Effectiveness

<img src="docs/figures/figure3_token_usage.png" width="680" alt="Token Usage Heatmap">

Request tokens stabilize after Iter0; response tokens shrink as models generate targeted patches rather than full rewrites.

| Tier | Cost/strategy | Overall Score | Models |
|------|--------------|---------------|--------|
| Premium | $0.82–1.03 | 7.29–7.85 | GPT-5.2, o3, Grok-4 Fast |
| Balanced | $0.39–0.40 | 6.94–7.44 | GPT-5.1, Grok-4.1 FR |
| Budget | $0.07–0.16 | 5.38–6.26 | GLM, DeepSeek, Gemini |

---

### Figure 4 — Code Quality Divergence Across LLMs

<img src="docs/figures/figure4_code_quality.png" width="680" alt="Code Quality Comparison">

Same frozen spec, five models — markedly different implementation quality. Common failures: silent semantic drift during bug fixes, incomplete audit logs despite passing backtests, look-ahead via `df.shift(-1)`. This motivates SysTB's hard validity gates and multi-dimensional scoring.

---

### Figure 5 — Iter0 Cross-Evaluation Arena Heatmap

<img src="docs/figures/figure5_arena_heatmap.png" width="680" alt="Arena Heatmap">

N×N cross-evaluation: every reviewer model scores every submitter on D1+D2 (self-reviews excluded). Top tier: **GPT-5.2 (7.73)**, **Grok-4 Fast (7.44)**, **o3 (7.29)**. Reviewer strictness varies: GPT-5.1 and o3 most critical (avg 6.8–7.0); Grok-4.1 FR and Grok-3 most generous (avg 8.0–8.3).

Sample rankings for 3 representative strategies: [`results/arena/cross_eval_ranking.csv`](results/arena/cross_eval_ranking.csv). Full per-strategy cross-evaluation results (17×17 matrices) are available upon request due to file size.

---

## Data

The benchmark uses **2024–2025 data** (24 months) across US daily equities, A-share daily, and crypto 1-min markets — 14 instruments total. Frozen time splits: Train/Dev 2024-01-01 ~ 2025-01-01, Test (OOS) 2025-01-01 ~ 2026-01-01.  
`sample_data/us_daily/AAPL.csv` is included for quick testing.  
To run the full benchmark, place your OHLCV CSVs per `configs/data_manifest.yaml`.

---

## Requirements

Python 3.9+ · pandas · numpy · pyyaml · openai · anthropic

```bash
pip install -r requirements.txt
```

> `configs/models.yaml` (API keys) is `.gitignore`d. Never commit it. Use `configs/models.yaml.template`.

---

