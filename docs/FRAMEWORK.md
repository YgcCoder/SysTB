# SysTradeBench Framework (paper §4)

This document summarizes the benchmark architecture from the paper *SysTradeBench: An Iterative Build–Test–Patch Benchmark for Strategy-to-Code Trading Systems with Drift-Aware Diagnostics* (KDD 2026). The repo aligns with this design.

## Three-layer architecture (Figure 1)

1. **Input Layer** (§4.2)  
   - Strategy Doc + Frozen Semantics (SHA256-frozen canonical JSON).  
   - Data suite: OHLCV, frozen time splits (Train/Dev [2024–2025), Test [2025–2026)).  
   - Evidence bundles for Iter k > 0: deployed code, scorecards D1–D4, gate failures, improvement suggestions.

2. **Model Generation Layer** (§4.3)  
   - Produces three mandatory artifacts:  
     - `strategy_card.json` (structured strategy interpretation).  
     - `strategy.py` (runnable code; interface `Strategy.run(market_data, initial_capital) -> (trade_log, audit_log)`).  
     - Mandatory audit logs: `logs/trade_log.csv`, `logs/audit_log.csv`.  
   - Iter0: zero-shot from Strategy Doc + Frozen Semantics.  
   - Iter1–3: evidence-driven patching (≤50 changed lines, frozen semantics).

3. **Evaluation Layer** (§4.4)  
   - **D1** Spec Fidelity: semantic equivalence to frozen spec; LLM cross-eval + drift checks.  
   - **D2** Risk Discipline: constraint compliance; LLM cross-eval.  
   - **D3** Reliability & Auditability: executability, determinism, anti-leakage, audit completeness; QR automated.  
   - **D4** OOS Robustness Indicators: execution success, Sharpe, drawdown, turnover, DSR/PBO signals; QR automated.  
   - **Arena**: N×N reviewers × submitters × strategies; D1/D2 scores 1–10; heatmap and model rankings (Figure 5).

4. **Executor** (§4.5)  
   - Sandboxed execution (no network, restricted FS, library whitelist).  
   - Validity gates: Parse, Schema, Exec, Determ, Anti-Leak, Audit.  
   - Drift-aware diagnostics: checksum + trace-based checks; drift → D1=0 and iteration invalidation.  
   - Iteration control: if k < 3 and D1–D3 < 0.85, trigger next iteration with evidence bundle; else output final arena rankings.

## Iterations

- **Iter0**: Zero-shot generation from Strategy Doc + Frozen Semantics.  
- **Iter1–Iter3**: Evidence-driven refinement. Input: evidence bundle (scorecard, failures, suggestions). Constraints: ≤50 changed lines, no semantic drift. Output: patched code + logs; re-run gates and D1–D4.

## Arena (model comparison)

- **Validité gates** (Table 3): per-model pass rates for Parse, Schema, Exec, Determ, Anti-Leak, Audit.  
- **Cross-evaluation** (Figure 5): each of N reviewer models scores each submitter on D1 and D2 (1–10). Self-reviews excluded. Aggregated scores → per-model ranking and heatmap (submitter × reviewer).  
- Result files in this repo: `results/arena/validity_gates.csv`, `results/arena/cross_eval_ranking.csv`. See `results/arena/README.md`.

## Logs in this repo

- `submission/logs/trade_log.csv` and `submission/logs/audit_log.csv` are **included** in the repo (sample run outputs) so that the full artifact set (strategy card, code, logs) is visible and reproducible.
