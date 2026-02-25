# SysTradeBench (SysTB)


**SysTradeBench** is the first benchmark to apply an iterative build–test–patch protocol with frozen-semantics constraints and drift-aware diagnostics for evaluating LLMs on full strategy-to-code generation in quantitative trading, featuring sandboxed execution, validity gates, and a cross-model arena.

> *SysTradeBench: An Iterative Build–Test–Patch Benchmark for Strategy-to-Code Trading Systems with Drift-Aware Diagnostics.* **KDD 2026.**

---

## Highlights

- **12 real-world trading strategies** across US equities, A-shares, and crypto — each with a frozen natural-language spec and semantic schema
- **20 frontier LLMs evaluated** (GPT-5, o3, Claude Opus/Sonnet, Gemini 3, Grok 4, DeepSeek-V3, GLM-4, Qwen3-Coder, ...)
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

# 4. Run the full pipeline (all 20 models × 12 strategies)
python scripts/run_experiment.py --config-dir configs --iter 0
```

---

## Full Iterative Pipeline

```bash
# ── Iter 0: Zero-shot generation ────────────────────────────────────────────
python scripts/run_experiment.py --config-dir configs --iter 0

# ── Arena: N×N cross-evaluation (per strategy) ──────────────────────────────
python scripts/cross_evaluation.py --strategy bollinger_mean_reversion

# ── Select Top-5 providers for refinement ───────────────────────────────────
python scripts/select_top_models.py --strategy bollinger_mean_reversion
# → writes results/iter1_iter2_models.yaml

# ── Iter 1 & 2: Evidence-driven refinement ──────────────────────────────────
python scripts/run_experiment.py --config-dir configs --iter 1
python scripts/run_experiment.py --config-dir configs --iter 2
```

Each submission is saved to `results/iter{N}_submissions/{model}/{strategy}/` with `generation/`, `submission/`, and `reports/` sub-folders.

---

## Framework

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  INPUT LAYER                                                 │
│  Strategy Doc (spec.md) + Frozen Semantics (spec.json)      │
│  OHLCV Data Suite · Evidence Bundle (Iter k > 0)            │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  MODEL GENERATION LAYER                                      │
│  strategy_card.json · strategy.py · trade_log · audit_log   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  EVALUATION LAYER                                            │
│  D1 Spec Fidelity (hard gate) · D2 Risk Discipline          │
│  D3 Reliability & Auditability (hard gate) · D4 OOS         │
│  Arena: N×N cross-evaluation heatmap                        │
└─────────────────────────────────────────────────────────────┘
```

### Validity Gates

`Parse → Schema → Exec → Determ → Anti-Leak → Audit`

Any gate failure short-circuits evaluation; Iter k results are invalidated on semantic drift.

### Iterations

| | Description | Models | Constraint |
|---|---|---|---|
| **Iter0** | Zero-shot generation | All 20 | None |
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

### Figure 1 — System Architecture and Iterative Workflow

![Architecture](docs/figures/figure1_architecture.png)

Three-layer pipeline: Input Layer (spec + frozen semantics + evidence bundle) → Model Generation Layer (strategy card + code + audit logs) → Evaluation Layer (D1–D4 scorecards + arena). The Executor runs sandboxed backtest, enforces validity gates, detects drift, and feeds the next evidence bundle.

---

### Figure 2 — RQ3: Evidence-Driven Repair Trajectories (Bollinger Mean Reversion)

![Learning Curves](docs/figures/figure2_learning_curves.png)

Learning curves for 3 top models across 4 iterations. Key findings:
- **Iter0→Iter1**: largest quality jump (+0.42 avg), dominated by D4 (+0.70) and D3 (+0.25) gains
- **Iter2**: code convergence trap — all models produce 95.4% similar code, OOS return drops to −4.6%
- **Iter3**: multi-objective recovery — explicit Sharpe/return targets break convergence, OOS return rebounds to +22.2%

---

### Figure 3 — RQ4: Token Usage and Cost-Effectiveness

![Token Usage](docs/figures/figure3_token_usage.png)

Token heatmap across 3 models × 4 iterations. Request tokens stabilize after Iter0; response tokens shrink as models generate targeted patches rather than full rewrites. Top models cost **$0.40–1.03/strategy** (Iter0); iteration adds ~50–60% cumulative cost.

| Tier | Cost/strategy | Overall Score | Models |
|------|--------------|---------------|--------|
| Premium | $0.82–1.03 | 7.29–7.85 | GPT-5.2, o3, Grok-4 Fast |
| Balanced | $0.39–0.40 | 6.94–7.44 | GPT-5.1, Grok-4.1 FR |
| Budget | $0.07–0.16 | 5.38–6.26 | GLM, DeepSeek, Gemini |

---

### Figure 4 — Illustrative Example: Code Quality Divergence Across LLMs

![Code Quality](docs/figures/figure4_code_quality.png)

Same frozen spec, five different models — markedly different implementation quality. Failures include: silent semantic drift during bug fixes, incomplete audit logs despite passing backtests, and look-ahead via `df.shift(-1)`. Motivates SysTB's hard gates + multi-dimensional scoring.

---

### Figure 5 — Iter0 Cross-Evaluation Arena Heatmap

![Arena Heatmap](docs/figures/figure5_arena_heatmap.png)

N×N cross-evaluation: every reviewer model scores every submitter on D1+D2 (self-reviews excluded). Top tier: **GPT-5.2 (7.73)**, **Grok-4 Fast (7.44)**, **o3 (7.29)**. Reviewer strictness varies: GPT-5.1 and o3 are most critical (avg 6.8–7.0); Grok-4.1 FR and Grok-3 most generous (avg 8.0–8.3). Raw rankings: [`results/arena/cross_eval_ranking.csv`](results/arena/cross_eval_ranking.csv).

---

## Data

The full dataset covers 2020–2026 across US daily, A-share daily, and crypto (1 min) markets.  
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


