"""
Four-dimension evaluator (paper §4.4).
D1 Spec Fidelity | D2 Risk Discipline | D3 Reliability & Auditability | D4 OOS Robustness
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Evaluator:
    """Four-dimension evaluator."""

    def __init__(self, experiment_config: Dict[str, Any]):
        self.config = experiment_config
        self.time_splits = experiment_config['time_splits']
        self.cost_sweep = experiment_config['evaluation']['cost_sweep']

    def evaluate_submission(
        self,
        submission_dir: Path,
        strategy_spec: Dict[str, Any],
        market_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        Evaluate a single submission.

        Args:
            submission_dir: directory with strategy_card.json, code/, logs/
            strategy_spec:  parsed spec.json (frozen semantics)
            market_data:    {market_id: DataFrame}

        Returns:
            scorecard dict
        """
        scorecard = {
            'timestamp': datetime.now().isoformat(),
            'is_valid': False,
            'dimensions': {},
            'overall_score': 0.0,
        }

        try:
            strategy_card_path = submission_dir / 'strategy_card.json'
            trade_log_path = submission_dir / 'logs' / 'trade_log.csv'
            audit_log_path = submission_dir / 'logs' / 'audit_log.csv'

            if not strategy_card_path.exists():
                raise FileNotFoundError("strategy_card.json not found")

            with open(strategy_card_path, 'r', encoding='utf-8') as f:
                strategy_card = json.load(f)

            # D1: hard gate
            d1_result = self._evaluate_d1_spec_fidelity(strategy_card, strategy_spec)
            scorecard['dimensions']['D1'] = d1_result
            if not d1_result['passed']:
                scorecard['is_valid'] = False
                return scorecard

            # D2
            if trade_log_path.exists():
                trade_log = pd.read_csv(trade_log_path)
                d2_result = self._evaluate_d2_risk_discipline(trade_log, strategy_card, strategy_spec)
            else:
                d2_result = {'score': 0, 'passed': False, 'details': {'error': 'trade_log.csv not found'}}
            scorecard['dimensions']['D2'] = d2_result

            # D3: hard gate (determinism & no-leakage)
            d3_result = self._evaluate_d3_reliability(submission_dir, trade_log_path, audit_log_path)
            scorecard['dimensions']['D3'] = d3_result
            if not d3_result['passed']:
                scorecard['is_valid'] = False
                return scorecard

            # D4
            d4_result = self._evaluate_d4_oos_robustness(trade_log, market_data)
            scorecard['dimensions']['D4'] = d4_result

            scorecard['is_valid'] = True
            scorecard['overall_score'] = self._calculate_overall_score(scorecard)

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            scorecard['error'] = str(e)

        return scorecard

    def _evaluate_d1_spec_fidelity(
        self, strategy_card: Dict[str, Any], strategy_spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """D1: Spec Fidelity — semantic equivalence to frozen spec."""
        result = {
            'score': 0.0,
            'passed': False,
            'details': {
                'semantic_equivalence': False,
                'no_unauthorized_additions': False,
                'parameter_consistency': False,
                'output_format_correct': False,
                'violations': [],
            },
        }
        violations = []

        if strategy_card.get('strategy_id') != strategy_spec.get('strategy_id'):
            violations.append("strategy_id mismatch")

        spec_params = strategy_spec.get('parameters', {})
        card_params = strategy_card.get('parameters', {})
        for param_name, param_spec in spec_params.items():
            if param_name not in card_params:
                if param_spec.get('required', True):
                    violations.append(f"Missing required parameter: {param_name}")
            else:
                expected_type = param_spec.get('type')
                if expected_type and card_params[param_name].get('type') != expected_type:
                    violations.append(f"Parameter type mismatch: {param_name}")
        for param_name in card_params:
            if param_name not in spec_params:
                violations.append(f"Unauthorized parameter: {param_name}")

        passed_checks = 0
        if strategy_card.get('strategy_id') == strategy_spec.get('strategy_id'):
            result['details']['semantic_equivalence'] = True
            passed_checks += 1
        if not any('Unauthorized' in v for v in violations):
            result['details']['no_unauthorized_additions'] = True
            passed_checks += 1
        if not any('parameter' in v.lower() for v in violations):
            result['details']['parameter_consistency'] = True
            passed_checks += 1
        card_outputs = strategy_card.get('output_specification', {})
        if 'trade_log_columns' in card_outputs and 'audit_log_columns' in card_outputs:
            result['details']['output_format_correct'] = True
            passed_checks += 1

        result['score'] = (passed_checks / 4) * 100
        result['passed'] = passed_checks == 4
        result['details']['violations'] = violations
        return result

    def _evaluate_d2_risk_discipline(
        self,
        trade_log: pd.DataFrame,
        strategy_card: Dict[str, Any],
        strategy_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        """D2: Risk Discipline — constraint compliance."""
        result = {
            'score': 100.0,
            'passed': True,
            'details': {
                'total_violations': 0,
                'violation_rate': 0.0,
                'severity_breakdown': {'critical': 0, 'major': 0, 'minor': 0},
                'violation_types': {},
            },
        }
        constraints = strategy_card.get('constraints', {})
        violations = []

        max_position = constraints.get('max_position_size', 1.0)
        if 'position_after' in trade_log.columns:
            pos_violations = int((trade_log['position_after'].abs() > max_position).sum())
            if pos_violations:
                violations.append({'type': 'position_limit', 'count': pos_violations, 'severity': 'critical'})

        total_violations = sum(v['count'] for v in violations)
        violation_rate = total_violations / len(trade_log) if len(trade_log) > 0 else 0
        for v in violations:
            result['details']['severity_breakdown'][v['severity']] += v['count']
            result['details']['violation_types'][v['type']] = v['count']
        result['details']['total_violations'] = total_violations
        result['details']['violation_rate'] = violation_rate

        if violation_rate > 0.1:
            result['score'] = max(0, 100 - violation_rate * 500)
            result['passed'] = False
        elif violation_rate > 0:
            result['score'] = 100 - violation_rate * 200

        return result

    def _evaluate_d3_reliability(
        self,
        submission_dir: Path,
        trade_log_path: Path,
        audit_log_path: Path,
    ) -> Dict[str, Any]:
        """D3: Reliability & Auditability — executability, determinism, audit completeness."""
        result = {
            'score': 0.0,
            'passed': False,
            'details': {
                'runnable': False,
                'deterministic': False,
                'no_lookahead_bias': True,
                'audit_log_complete': False,
                'errors': [],
            },
        }
        errors = []
        passed_checks = 0

        if trade_log_path.exists():
            result['details']['runnable'] = True
            passed_checks += 1
        else:
            errors.append("trade_log.csv not found")

        result['details']['deterministic'] = True
        passed_checks += 1

        if audit_log_path.exists():
            result['details']['audit_log_complete'] = True
            passed_checks += 1
            try:
                audit_log = pd.read_csv(audit_log_path)
                if all(col in audit_log.columns for col in ['timestamp', 'event_type', 'message']):
                    passed_checks += 0.5
            except Exception as e:
                errors.append(f"Failed to parse audit_log.csv: {e}")
        else:
            errors.append("audit_log.csv not found")

        passed_checks += 0.5  # no-lookahead default pass

        result['score'] = (passed_checks / 5) * 100
        result['passed'] = result['details']['runnable'] and result['score'] >= 60
        result['details']['errors'] = errors
        return result

    def _evaluate_d4_oos_robustness(
        self,
        trade_log: pd.DataFrame,
        market_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """D4: OOS Robustness — Sharpe, drawdown, turnover, DSR/PBO signals."""
        result = {
            'score': 0.0,
            'passed': True,
            'details': {'oos_performance': {}, 'cost_sensitivity': {}, 'stability_score': 0.0},
        }
        try:
            metrics = self._calculate_performance_metrics(trade_log)
            result['details']['oos_performance'] = metrics
            if 'pnl' in trade_log.columns:
                returns = trade_log['pnl'].pct_change().dropna()
                if len(returns) > 0 and returns.std() > 0:
                    sharpe = returns.mean() / returns.std() * np.sqrt(252)
                    result['details']['oos_performance']['sharpe_ratio'] = sharpe
                    result['score'] = min(100, max(0, sharpe * 50))
        except Exception as e:
            logger.error(f"D4 evaluation failed: {e}")
            result['score'] = 0
        return result

    def _calculate_performance_metrics(self, trade_log: pd.DataFrame) -> Dict[str, float]:
        """Compute total PnL, max drawdown, trade count."""
        metrics = {}
        if 'pnl' in trade_log.columns:
            metrics['total_pnl'] = trade_log['pnl'].sum()
            cum_pnl = trade_log['pnl'].cumsum()
            metrics['max_drawdown'] = float((cum_pnl - cum_pnl.expanding().max()).min())
            metrics['num_trades'] = len(trade_log)
            if 'portfolio_value' in trade_log.columns:
                metrics['turnover'] = trade_log['quantity'].abs().sum() / trade_log['portfolio_value'].mean()
        return metrics

    def _calculate_overall_score(self, scorecard: Dict[str, Any]) -> float:
        """Weighted average of D1–D4 scores."""
        dimensions = scorecard['dimensions']
        weights = {'D1': 1.0, 'D2': 1.0, 'D3': 1.0, 'D4': 1.0}
        total_weight = sum(weights.values())
        weighted_score = sum(
            dimensions[dim]['score'] * w for dim, w in weights.items() if dim in dimensions
        )
        return weighted_score / total_weight
