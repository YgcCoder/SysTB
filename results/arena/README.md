# Cross-evaluation arena (paper §4.4.5, Figure 5)

This folder contains **model comparison scores** from the SysTradeBench evaluation (paper *SysTradeBench: An Iterative Build–Test–Patch Benchmark for Strategy-to-Code Trading Systems with Drift-Aware Diagnostics*, KDD 2026).

## Files

- **validity_gates.csv** — Per-model validity gate pass rates (paper Table 3). Columns: model, strategies, parse_pct, schema_pct, exec_pct, determ_pct, anti_leak_pct, audit_pct. Top models (e.g. GPT-5.2, Grok-4 Fast, o3) achieve ≥91.7% on all gates.
- **cross_eval_ranking.csv** — LLM cross-evaluation arena: per-strategy submitter ranking by average D1 (Spec Fidelity) and D2 (Risk Discipline) score (1–10 scale), number of reviews, and rank. Used for aggregate model rankings and heatmaps (paper Figure 5).

## Arena protocol (paper §4.4.5)

- **N models × N reviewers × strategies**: each reviewer LLM scores each submitter’s submission on D1 and D2 with structured rubrics.
- **Self-reviews** are excluded from final rankings to control bias.
- **Aggregation**: average peer-only scores yield per-model rankings; heatmap rows = submitter, columns = reviewer, cell = average score.

Full heatmap data (reviewer × submitter × strategy) is produced by the benchmark scripts; this CSV is a summary for the repo.
