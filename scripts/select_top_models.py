"""
Select Top-5 providers for Iter1/Iter2 based on Iter0 cross-evaluation scores.
Outputs results/iter1_iter2_models.yaml used by run_experiment.py.

Usage:
  cd github
  python scripts/select_top_models.py --strategy bollinger_mean_reversion
  python scripts/select_top_models.py --strategy bollinger_mean_reversion --top-n 5
"""
import sys
import json
import yaml
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_cross_evaluations(results_dir: Path, strategy_id: str, iter_num: int = 0) -> Dict[str, Dict]:
    """
    Load cross-evaluation results for all models.

    Returns:
        {generator_model: {evaluator_model: evaluation_dict}}
    """
    cross_evals: Dict[str, Dict] = {}

    # New layout: results/iter0_submissions/{model}/{strategy}/cross_evaluations.json
    iter_dir = results_dir / f'iter{iter_num}_submissions'
    if iter_dir.exists():
        for model_dir in iter_dir.iterdir():
            if not model_dir.is_dir():
                continue
            f = model_dir / strategy_id / "cross_evaluations.json"
            if f.exists():
                with open(f, 'r', encoding='utf-8') as fh:
                    cross_evals[model_dir.name] = json.load(fh)
    else:
        # Legacy layout
        for model_dir in results_dir.iterdir():
            if not model_dir.is_dir():
                continue
            f = model_dir / strategy_id / f"iter{iter_num}" / "cross_evaluations.json"
            if f.exists():
                with open(f, 'r', encoding='utf-8') as fh:
                    cross_evals[model_dir.name] = json.load(fh)

    return cross_evals


def calculate_peer_scores(cross_evals: Dict[str, Dict]) -> Dict[str, float]:
    """
    Average D1+D2 score per submitter, excluding self-reviews.

    Returns:
        {model_id: average_peer_score}
    """
    avg_scores: Dict[str, float] = {}
    for generator, evaluations in cross_evals.items():
        scores = []
        for evaluator, eval_data in evaluations.items():
            if evaluator == generator:
                continue  # exclude self-review
            if eval_data.get('status') == 'success':
                d1 = eval_data.get('D1_spec_fidelity', {}).get('score', 0)
                d2 = eval_data.get('D2_risk_discipline', {}).get('score', 0)
                avg = (d1 + d2) / 2
                if avg > 0:
                    scores.append(avg)
        avg_scores[generator] = sum(scores) / len(scores) if scores else 0.0
    return avg_scores


def group_by_provider(models: List[str]) -> Dict[str, List[str]]:
    """Group model IDs by provider family."""
    providers: Dict[str, List[str]] = defaultdict(list)
    for model in models:
        m = model.lower()
        if 'gpt' in m or m.startswith('o3') or m.startswith('o1'):
            providers['OpenAI'].append(model)
        elif 'claude' in m:
            providers['Anthropic'].append(model)
        elif 'gemini' in m:
            providers['Google'].append(model)
        elif 'deepseek' in m or 'doubao' in m or m.startswith('ark'):
            providers['DeepSeek/Ark'].append(model)
        elif 'qwen' in m or 'fireworks' in m:
            providers['Qwen/Fireworks'].append(model)
        elif 'glm' in m:
            providers['GLM'].append(model)
        elif 'grok' in m:
            providers['xAI/Grok'].append(model)
        else:
            providers['Others'].append(model)
    return dict(providers)


def best_model_per_provider(
    avg_scores: Dict[str, float],
    providers: Dict[str, List[str]],
) -> Dict[str, Tuple[str, float]]:
    """For each provider, pick the highest-scoring model."""
    provider_best: Dict[str, Tuple[str, float]] = {}
    for provider, models in providers.items():
        best = max(models, key=lambda m: avg_scores.get(m, 0.0), default=None)
        if best:
            provider_best[provider] = (best, avg_scores.get(best, 0.0))
    return provider_best


def save_iter1_2_config(
    top_providers: List[Tuple[str, str, float]],
    results_dir: Path,
) -> Path:
    """Write results/iter1_iter2_models.yaml for use by run_experiment.py."""
    config = {
        'description': 'Top providers for Iter1/Iter2 — auto-selected from Iter0 cross-evaluation',
        'generated_at': datetime.now().isoformat(),
        'models': [
            {'model_name': model, 'provider': provider, 'iter0_avg_score': round(score, 2)}
            for provider, model, score in top_providers
        ],
    }
    out = results_dir / 'iter1_iter2_models.yaml'
    with open(out, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"[OK] Iter1/2 config saved: {out}")
    return out


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Select Top-N providers for Iter1/Iter2')
    parser.add_argument('--strategy', required=True, help='Strategy ID')
    parser.add_argument('--results-dir', default='results', help='Results directory (default: results)')
    parser.add_argument('--top-n', type=int, default=5, help='Number of top providers to select (default: 5)')
    parser.add_argument('--iter', type=int, default=0, help='Iter whose cross-evals to use (default: 0)')
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()

    print("=" * 70)
    print("Auto-select Top Providers for Iter1/Iter2")
    print("=" * 70)
    print(f"Strategy   : {args.strategy}")
    print(f"Results dir: {results_dir}")

    # 1. Load cross-evaluation results
    print(f"\n[1/4] Loading cross-evaluation results (iter{args.iter})...")
    cross_evals = load_cross_evaluations(results_dir, args.strategy, args.iter)
    print(f"      Found {len(cross_evals)} models")

    if not cross_evals:
        print("ERROR: No cross-evaluation results found.")
        print(f"       Run: python scripts/cross_evaluation.py --strategy {args.strategy}")
        return 1

    # 2. Calculate peer-only scores (D1+D2 avg, self excluded)
    print("\n[2/4] Computing peer scores (self-reviews excluded)...")
    avg_scores = calculate_peer_scores(cross_evals)
    print("\n  Model rankings:")
    for model, score in sorted(avg_scores.items(), key=lambda x: x[1], reverse=True):
        print(f"    {model:<55} {score:.2f}")

    # 3. Group by provider, pick best per provider
    print("\n[3/4] Grouping by provider...")
    providers = group_by_provider(list(avg_scores.keys()))
    for p, ms in providers.items():
        print(f"    {p}: {len(ms)} model(s)")

    provider_best = best_model_per_provider(avg_scores, providers)

    # 4. Rank providers, take Top N
    print(f"\n[4/4] Selecting Top {args.top_n} providers...")
    sorted_providers = sorted(provider_best.items(), key=lambda x: x[1][1], reverse=True)

    print(f"\n  All providers ranked:")
    print(f"  {'#':<4} {'Provider':<25} {'Score':>6}  Model")
    print("  " + "-" * 70)
    top_providers: List[Tuple[str, str, float]] = []
    for i, (provider, (model, score)) in enumerate(sorted_providers, 1):
        tag = " ← selected" if i <= args.top_n else ""
        print(f"  {i:<4} {provider:<25} {score:>6.2f}  {model}{tag}")
        if i <= args.top_n:
            top_providers.append((provider, model, score))

    # Save config
    out_path = save_iter1_2_config(top_providers, results_dir)

    print("\n" + "=" * 70)
    print(f"[OK] Selected {len(top_providers)} models for Iter1/Iter2:")
    for i, (provider, model, score) in enumerate(top_providers, 1):
        print(f"  {i}. {model}  (provider: {provider}, score: {score:.2f})")

    print(f"\nNext step:")
    print(f"  python scripts/run_experiment.py --config-dir configs --iter 1 --strategies {args.strategy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
