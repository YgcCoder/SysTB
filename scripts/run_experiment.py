"""
Main experiment runner: Iter0 (zero-shot) -> Iter1-N (evidence-driven refinement).

Usage:
  cd github
  python scripts/run_experiment.py --config-dir configs --iter 0
  python scripts/run_experiment.py --config-dir configs --iter 1 --models gpt_5_2 o3
  python scripts/run_experiment.py --config-dir configs   # run full Iter0->Iter2
"""
import sys
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import DataLoader, ModelClientFactory, Evaluator
from harness.code_executor import CodeExecutor
from harness.data_sampler import DataSampler
from harness.path_sanitizer import PathSanitizer, SanitizedLogger
from harness.response_parser import ResponseParserV2

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Orchestrates the full SysTradeBench experiment pipeline."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir

        logger.info("Loading configurations...")
        with open(config_dir / 'experiment.yaml', 'r', encoding='utf-8') as f:
            self.experiment_config = yaml.safe_load(f)

        self.sanitizer = PathSanitizer(config_dir.parent)
        self.sanitized_logger = SanitizedLogger(__name__, self.sanitizer)

        logger.info("Initializing components...")
        self.data_loader = DataLoader(str(config_dir / 'data_manifest.yaml'))
        self.data_sampler = DataSampler(self.data_loader)
        self.model_clients = ModelClientFactory.load_models_config(str(config_dir / 'models.yaml'))
        self.evaluator = Evaluator(self.experiment_config)
        self.code_executor = CodeExecutor(self.experiment_config['time_splits'])
        self.response_parser = ResponseParserV2()

        self.results_dir = config_dir.parent / 'results'
        self.results_dir.mkdir(exist_ok=True)

        logger.info(f"Loaded {len(self.model_clients)} model clients")

    # ------------------------------------------------------------------
    # Strategy spec loading
    # ------------------------------------------------------------------

    def load_strategy_spec(self, strategy_id: str) -> Dict[str, Any]:
        strategy_config = self._get_strategy_config(strategy_id)
        spec_path = Path(strategy_config['spec_path']) / 'spec.json'
        with open(spec_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_strategy_prompt(self, strategy_id: str) -> str:
        strategy_config = self._get_strategy_config(strategy_id)
        spec_path = Path(strategy_config['spec_path']) / 'spec.md'
        return spec_path.read_text(encoding='utf-8')

    def _get_strategy_config(self, strategy_id: str) -> Dict[str, Any]:
        for s in self.experiment_config['strategies']:
            if s['strategy_id'] == strategy_id:
                return s
        raise ValueError(f"Strategy {strategy_id} not found in experiment.yaml")

    # ------------------------------------------------------------------
    # Iter0: zero-shot generation
    # ------------------------------------------------------------------

    def run_iter0(self, model_id: str, strategy_id: str) -> Path:
        logger.info(f"[Iter0] {model_id} x {strategy_id}")

        submission_dir = self.results_dir / 'iter0_submissions' / model_id / strategy_id
        for sub in ['submission/code', 'submission/logs', 'generation', 'evaluation']:
            (submission_dir / sub).mkdir(parents=True, exist_ok=True)

        try:
            strategy_spec = self.load_strategy_spec(strategy_id)
            strategy_prompt = self.load_strategy_prompt(strategy_id)

            system_prompt = self._load_system_prompt()
            full_prompt = self._build_iter0_prompt(strategy_prompt, strategy_spec, strategy_id)

            logger.info(f"Generating code with {model_id}...")
            client = self.model_clients[model_id]
            response = client.generate_with_retry(full_prompt, system_prompt)

            sanitized_response = self.sanitizer.sanitize(response)
            (submission_dir / 'generation' / 'model_response.txt').write_text(sanitized_response, encoding='utf-8')
            (submission_dir / 'generation' / 'prompt_used.txt').write_text(
                self.sanitizer.sanitize(full_prompt), encoding='utf-8'
            )
            (submission_dir / 'generation' / 'metadata.json').write_text(
                json.dumps({
                    'submitter_model': model_id,
                    'strategy_id': strategy_id,
                    'iteration': 0,
                    'timestamp': datetime.now().isoformat(),
                    'prompt_length': len(full_prompt),
                    'response_length': len(response),
                }, indent=2),
                encoding='utf-8',
            )

            logger.info("Parsing model response...")
            submission_output_dir = submission_dir / 'submission'
            parse_success, parse_error = self.response_parser.parse_with_fallback(response, submission_output_dir)
            if not parse_success:
                logger.error(f"Failed to parse response: {parse_error}")
                (submission_dir / 'generation' / 'parse_error.txt').write_text(parse_error, encoding='utf-8')

            strategy_card_path = submission_dir / 'submission' / 'strategy_card.json'
            if strategy_card_path.exists():
                with open(strategy_card_path, 'r', encoding='utf-8') as f:
                    strategy_card = json.load(f)

                strategy_config = self._get_strategy_config(strategy_id)
                market_id = strategy_config.get('markets', ['us_daily'])[0]
                symbols = self.data_loader.get_available_symbols(market_id)

                if symbols:
                    test_split = self.experiment_config['time_splits']['public_test']
                    market_data = self.data_loader.load_market_data(
                        market_id, symbols[0],
                        test_split['time_min'], test_split['time_max'],
                    )

                    success, error_msg = self.code_executor.execute_strategy(
                        submission_output_dir, market_data, strategy_card
                    )

                    if success:
                        logger.info("Strategy executed successfully")
                        scorecard = self.evaluator.evaluate_submission(
                            submission_output_dir, strategy_spec, {market_id: market_data}
                        )
                        reports_dir = submission_dir / 'reports'
                        reports_dir.mkdir(exist_ok=True)
                        with open(reports_dir / 'scorecard.json', 'w', encoding='utf-8') as f:
                            json.dump(scorecard, f, indent=2)
                        logger.info(f"Overall score: {scorecard.get('overall_score', 0):.2f}")
                    else:
                        logger.error(f"Strategy execution failed: {error_msg}")
                        (submission_dir / 'execution_error.txt').write_text(error_msg, encoding='utf-8')

        except Exception as e:
            logger.error(f"Iter0 failed: {e}", exc_info=True)
            (submission_dir / 'error.txt').write_text(str(e), encoding='utf-8')

        return submission_dir

    # ------------------------------------------------------------------
    # Iter N: evidence-driven refinement
    # ------------------------------------------------------------------

    def run_iter_n(
        self,
        model_id: str,
        strategy_id: str,
        iter_num: int,
        previous_result_dir: Path,
    ) -> Path:
        logger.info(f"[Iter{iter_num}] {model_id} x {strategy_id}")

        result_dir = self.results_dir / model_id / strategy_id / f'iter{iter_num}'
        result_dir.mkdir(parents=True, exist_ok=True)

        try:
            evidence_path = previous_result_dir / 'reports' / 'evidence_bundle.md'
            evidence = evidence_path.read_text(encoding='utf-8') if evidence_path.exists() else \
                "No feedback available from previous iteration."

            strategy_spec = self.load_strategy_spec(strategy_id)
            system_prompt = self._load_system_prompt()
            full_prompt = self._build_iter_n_prompt(evidence, strategy_spec)

            logger.info(f"Generating patch with {model_id}...")
            response = self.model_clients[model_id].generate_with_retry(full_prompt, system_prompt)
            (result_dir / 'model_response.txt').write_text(response, encoding='utf-8')

        except Exception as e:
            logger.error(f"Iter{iter_num} failed: {e}", exc_info=True)
            (result_dir / 'error.txt').write_text(str(e), encoding='utf-8')

        return result_dir

    # ------------------------------------------------------------------
    # Full experiment orchestration
    # ------------------------------------------------------------------

    def run_full_experiment(
        self,
        model_ids: Optional[List[str]] = None,
        strategy_ids: Optional[List[str]] = None,
    ):
        if model_ids is None:
            model_ids = list(self.model_clients.keys())
        if strategy_ids is None:
            strategy_ids = [s['strategy_id'] for s in self.experiment_config['strategies']]

        num_iterations = self.experiment_config['iteration']['num_iterations']

        logger.info("=" * 80)
        logger.info("Starting Full Experiment")
        logger.info(f"  Strategies : {strategy_ids}")
        logger.info(f"  Iter0 models: {len(model_ids)}")
        logger.info(f"  Total iterations: 0 to {num_iterations}")
        logger.info("=" * 80)

        # Phase 1: Iter0
        logger.info(f"\n{'='*80}\nPHASE 1: Iter0 — Zero-shot ({len(model_ids)} models)\n{'='*80}")
        for model_id in model_ids:
            for strategy_id in strategy_ids:
                try:
                    self.run_iter0(model_id, strategy_id)
                except Exception as e:
                    logger.error(f"Iter0 failed for {model_id} x {strategy_id}: {e}", exc_info=True)

        logger.info(f"\nIter0 done for all {len(model_ids)} models.")
        logger.info("Next: run cross_evaluation.py, then select_top_models.py before Iter1/2.")

        # Phase 2: Iter1+
        if num_iterations > 0:
            logger.info(f"\n{'='*80}\nPHASE 2: Iter1-{num_iterations} — Refinement\n{'='*80}")
            iter1_model_ids = self._load_iter1_2_models()
            for iter_num in range(1, num_iterations + 1):
                for model_id in iter1_model_ids:
                    for strategy_id in strategy_ids:
                        try:
                            prev_dir = self.results_dir / model_id / strategy_id / f'iter{iter_num - 1}'
                            self.run_iter_n(model_id, strategy_id, iter_num, prev_dir)
                        except Exception as e:
                            logger.error(f"Iter{iter_num} failed: {e}", exc_info=True)

        logger.info("\n[OK] Full experiment completed!")

    def run_single_iteration(
        self,
        iteration: int,
        model_ids: Optional[List[str]] = None,
        strategy_ids: Optional[List[str]] = None,
    ):
        if strategy_ids is None:
            strategy_ids = [s['strategy_id'] for s in self.experiment_config['strategies']]
        if model_ids is None:
            if iteration == 0:
                model_ids = list(self.model_clients.keys())
            else:
                model_ids = self._load_iter1_2_models()

        logger.info(f"{'='*80}\nIteration {iteration} | {len(model_ids)} models | {len(strategy_ids)} strategies\n{'='*80}")

        for model_id in model_ids:
            for strategy_id in strategy_ids:
                try:
                    if iteration == 0:
                        self.run_iter0(model_id, strategy_id)
                    else:
                        prev_dir = self.results_dir / model_id / strategy_id / f'iter{iteration - 1}'
                        self.run_iter_n(model_id, strategy_id, iteration, prev_dir)
                except Exception as e:
                    logger.error(f"Iter{iteration} failed for {model_id} x {strategy_id}: {e}", exc_info=True)

        logger.info(f"\n[OK] Iter{iteration} completed")

    def _load_iter1_2_models(self) -> List[str]:
        iter1_config = self.results_dir / 'iter1_iter2_models.yaml'
        if iter1_config.exists():
            with open(iter1_config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            model_names = [m['model_name'] for m in config['models']]
            model_ids = [cid for cid, c in self.model_clients.items() if c.model_name in model_names]
            logger.info(f"Loaded {len(model_ids)} Top models for Iter1/2")
            return model_ids
        logger.warning("iter1_iter2_models.yaml not found. Run select_top_models.py first.")
        return list(self.model_clients.keys())

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _load_system_prompt(self) -> str:
        p = self.config_dir / 'prompts' / 'system_prompt.md'
        return p.read_text(encoding='utf-8') if p.exists() else \
            "You are an expert quantitative trading strategist and Python programmer."

    def _build_iter0_prompt(self, strategy_md: str, strategy_spec: Dict, strategy_id: str) -> str:
        strategy_config = self._get_strategy_config(strategy_id)
        markets = strategy_config.get('markets', ['us_daily'])
        data_sample = self.sanitizer.sanitize(
            self.data_sampler.generate_data_sample_prompt(market_id=markets[0], num_rows=10)
        )
        return f"""# Task: Implement Quantitative Trading Strategy

Please implement the following trading strategy according to the specification.

## Strategy Specification

{strategy_md}

{data_sample}

## Output Requirements

Provide **two artifacts**:

1. **strategy_card.json**  
2. **strategy.py** with interface:

```python
class Strategy:
    def __init__(self, config: dict): ...
    def run(self, market_data: pd.DataFrame, initial_capital: float = 100000.0):
        # Returns (trade_log_df, audit_log_df)
```

Logs must include:
- `trade_log.csv`: columns [timestamp, symbol, action, quantity, price, cost, pnl, ...]
- `audit_log.csv`: columns [timestamp, event_type, message, ...]

## Rules

- Follow spec strictly; do NOT add unauthorised indicators or parameters
- No lookahead bias (never use future bars)
- Deterministic: same input → same output
- Robust error handling
- **ALL code, comments, logs MUST be in English only**

Please provide your complete implementation now.
"""

    def _build_iter_n_prompt(self, evidence: str, strategy_spec: Dict) -> str:
        return f"""# Task: Refine Strategy Implementation Based on Feedback

## Evaluation Feedback

{evidence}

## Instructions

Fix identified issues. You may:
- Fix bugs
- Improve constraint compliance
- Improve robustness

You must NOT:
- Change core strategy semantics
- Add unauthorised features
- Modify frozen parameters without justification

Provide your patch or updated implementation.
"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description='SysTradeBench Experiment Runner')
    parser.add_argument('--config-dir', default='configs', help='Config directory (default: configs)')
    parser.add_argument('--models', nargs='+', help='Model IDs (default: all enabled)')
    parser.add_argument('--strategies', nargs='+', help='Strategy IDs (default: all)')
    parser.add_argument('--iter', type=int, choices=[0, 1, 2], help='Run specific iteration only')
    args = parser.parse_args()

    config_dir = Path(args.config_dir).resolve()
    runner = ExperimentRunner(config_dir)

    if args.iter is None:
        runner.run_full_experiment(args.models, args.strategies)
    else:
        runner.run_single_iteration(args.iter, args.models, args.strategies)

    logger.info("\n[OK] All done!")


if __name__ == "__main__":
    main()
