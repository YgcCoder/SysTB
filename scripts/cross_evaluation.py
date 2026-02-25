"""
Cross-evaluation module (paper §4.4.5, Figure 5).
After Iter0, every reviewer model scores every submitter's code on D1 and D2 (1-10).
Self-reviews are excluded from final rankings.

Usage:
  cd github
  python scripts/cross_evaluation.py --strategy bollinger_mean_reversion
  python scripts/cross_evaluation.py --strategy bollinger_mean_reversion --results-dir results
"""
import sys
import json
import re
import yaml
from pathlib import Path
from typing import Dict, List
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import ModelClientFactory
from harness.path_sanitizer import PathSanitizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CrossEvaluator:
    """N×N arena cross-evaluator."""

    def __init__(self, models_config_path: str):
        self.model_clients = ModelClientFactory.load_models_config(models_config_path)
        self.sanitizer = PathSanitizer()
        logger.info(f"Loaded {len(self.model_clients)} model clients for cross-evaluation")

    def evaluate_single_submission(
        self,
        evaluator_model_id: str,
        submission_dir: Path,
        strategy_spec: Dict,
    ) -> Dict:
        """
        Have one reviewer model score one submission.

        Args:
            evaluator_model_id: the reviewing model
            submission_dir:     submission directory (contains strategy_card.json + code/)
            strategy_spec:      frozen spec.json dict

        Returns:
            evaluation dict with scores and comments
        """
        try:
            strategy_card_path = submission_dir / "strategy_card.json"
            code_path = submission_dir / "code" / "strategy.py"

            if not strategy_card_path.exists() or not code_path.exists():
                return {'evaluator': evaluator_model_id, 'status': 'error', 'error': 'Missing files'}

            with open(strategy_card_path, 'r', encoding='utf-8') as f:
                strategy_card = json.load(f)
            with open(code_path, 'r', encoding='utf-8') as f:
                code = f.read()

            eval_prompt = self._build_eval_prompt(strategy_spec, strategy_card, code)
            client = self.model_clients[evaluator_model_id]
            response = client.generate_with_retry(eval_prompt)

            evaluation = self._parse_evaluation(response)
            evaluation['evaluator'] = evaluator_model_id
            return evaluation

        except Exception as e:
            logger.error(f"Evaluation failed ({evaluator_model_id}): {e}")
            return {'evaluator': evaluator_model_id, 'status': 'error', 'error': str(e)}

    def cross_evaluate_all(
        self,
        results_dir: Path,
        strategy_id: str,
        strategy_spec: Dict,
        iter_num: int = 0,
    ) -> Dict[str, Dict]:
        """
        Cross-evaluate all submissions for one strategy.

        Each submitter's code is reviewed by all other models (self-reviews excluded
        when computing rankings).

        Returns:
            {generator_model: {evaluator_model: evaluation_dict}}
        """
        logger.info(f"Starting cross-evaluation | strategy: {strategy_id} | iter: {iter_num}")

        # Collect submissions
        submissions: Dict[str, Path] = {}
        iter_dir = results_dir / f'iter{iter_num}_submissions'
        if iter_dir.exists():
            for model_dir in iter_dir.iterdir():
                if not model_dir.is_dir():
                    continue
                sub_dir = model_dir / strategy_id / 'submission'
                if sub_dir.exists():
                    submissions[model_dir.name] = sub_dir
        else:
            # Legacy flat layout
            for model_dir in results_dir.iterdir():
                if not model_dir.is_dir():
                    continue
                sub_dir = model_dir / strategy_id / f'iter{iter_num}'
                if sub_dir.exists():
                    submissions[model_dir.name] = sub_dir

        logger.info(f"Found {len(submissions)} submissions to evaluate")

        cross_eval_matrix: Dict[str, Dict] = {}

        for generator_model, submission_dir in submissions.items():
            logger.info(f"\nEvaluating submission from: {generator_model}")
            evaluations: Dict[str, Dict] = {}

            for evaluator_model in self.model_clients.keys():
                logger.info(f"  Reviewer: {evaluator_model}")
                evaluation = self.evaluate_single_submission(
                    evaluator_model, submission_dir, strategy_spec
                )
                evaluations[evaluator_model] = evaluation

            cross_eval_matrix[generator_model] = evaluations

            # Save per-submission results
            out_file = submission_dir.parent / "cross_evaluations.json"
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(evaluations, f, indent=2)

        return cross_eval_matrix

    def _build_eval_prompt(self, strategy_spec: Dict, strategy_card: Dict, code: str) -> str:
        """Build the reviewer prompt for D1/D2 scoring."""
        code_sanitized = self.sanitizer.sanitize(code)
        return f"""# Task: Evaluate Strategy Implementation (D1 Spec Fidelity & D2 Risk Discipline)

You are an expert quantitative trading strategist. Evaluate the implementation below.

## Original Strategy Specification

Strategy ID: {strategy_spec.get('strategy_id', 'N/A')}
Strategy Name: {strategy_spec.get('strategy_name', 'N/A')}

Required Parameters:
```json
{json.dumps(strategy_spec.get('parameters', {}), indent=2)}
```

## Implementation Under Review

### strategy_card.json
```json
{json.dumps(strategy_card, indent=2)}
```

### strategy.py (first 5000 chars)
```python
{code_sanitized[:5000]}
```

## Scoring Dimensions

Score each on a 1–10 integer scale:

**D1 — Spec Fidelity**
- Does the implementation follow the specification exactly?
- Are all required parameters present with correct types?
- No unauthorized indicators or parameters added?

**D2 — Risk Discipline**
- Are position limits and leverage constraints respected?
- No lookahead bias (future data usage)?
- Edge cases handled (zero-division, missing data, boundary)?

## Output Format

Respond with a JSON block only:

```json
{{
  "D1_spec_fidelity": {{
    "score": <1-10>,
    "comment": "<brief reasoning>"
  }},
  "D2_risk_discipline": {{
    "score": <1-10>,
    "comment": "<brief reasoning>"
  }},
  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "recommendation": "ACCEPT|REVISE|REJECT"
}}
```
"""

    def _parse_evaluation(self, response: str) -> Dict:
        """Extract the JSON evaluation block from the model response."""
        match = re.search(r'```json\s*\n(.*?)\n```', response, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                evaluation = json.loads(match.group(1))
                evaluation['status'] = 'success'
                evaluation['raw_response_excerpt'] = response[:300]
                return evaluation
            except json.JSONDecodeError:
                pass
        return {'status': 'parse_failed', 'raw_response': response[:1000]}

    def generate_cross_eval_report(self, cross_eval_matrix: Dict[str, Dict], output_file: Path):
        """Generate a markdown cross-evaluation heatmap table."""
        evaluators = list(self.model_clients.keys())
        lines = [
            "# Cross-Evaluation Arena Report",
            "",
            f"Total Submitters : {len(cross_eval_matrix)}",
            f"Total Reviewers  : {len(evaluators)}",
            "",
            "## D1+D2 Score Matrix (avg per cell; — = self-review excluded)",
            "",
            "| Submitter \\ Reviewer | " + " | ".join(evaluators) + " | **Avg (excl. self)** |",
            "|" + "|".join(["---"] * (len(evaluators) + 2)) + "|",
        ]

        for generator, evaluations in sorted(cross_eval_matrix.items()):
            peer_scores = []
            row = f"| {generator} |"
            for evaluator in evaluators:
                eval_data = evaluations.get(evaluator, {})
                if evaluator == generator:
                    row += " — |"
                elif eval_data.get('status') == 'success':
                    d1 = eval_data.get('D1_spec_fidelity', {}).get('score', 0)
                    d2 = eval_data.get('D2_risk_discipline', {}).get('score', 0)
                    avg = (d1 + d2) / 2
                    peer_scores.append(avg)
                    row += f" {avg:.1f} |"
                else:
                    row += " err |"
            overall = f"{sum(peer_scores)/len(peer_scores):.2f}" if peer_scores else "N/A"
            row += f" **{overall}** |"
            lines.append(row)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        logger.info(f"Cross-evaluation report saved: {output_file}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SysTradeBench Cross-Evaluation (Arena)')
    parser.add_argument('--strategy', required=True, help='Strategy ID (e.g. bollinger_mean_reversion)')
    parser.add_argument('--results-dir', default='results', help='Results directory (default: results)')
    parser.add_argument('--iter', type=int, default=0, help='Iteration number to evaluate (default: 0)')
    args = parser.parse_args()

    config_dir = Path(__file__).resolve().parent.parent / "configs"
    results_dir = Path(args.results_dir).resolve()

    evaluator = CrossEvaluator(str(config_dir / "models.yaml"))

    # Load strategy spec
    strategy_spec = {'strategy_id': args.strategy}
    spec_candidates = list((Path(__file__).resolve().parent.parent / 'strategy').glob(f'*{args.strategy.replace("_", " ")}*/spec.json'))
    if spec_candidates:
        with open(spec_candidates[0], 'r', encoding='utf-8') as f:
            strategy_spec = json.load(f)
        logger.info(f"Loaded spec from {spec_candidates[0]}")

    cross_eval_matrix = evaluator.cross_evaluate_all(results_dir, args.strategy, strategy_spec, args.iter)

    report_file = results_dir / f"{args.strategy}_iter{args.iter}_cross_evaluation.md"
    evaluator.generate_cross_eval_report(cross_eval_matrix, report_file)

    print(f"\n[OK] Cross-evaluation completed")
    print(f"     Report: {report_file}")


if __name__ == "__main__":
    main()
