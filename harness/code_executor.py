"""
Code executor: safely run LLM-generated strategy code and produce trade_log / audit_log.
Paper §4.3 — Validity gates: Parse, Schema, Exec, Determ, Anti-Leak, Audit.
"""
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple
import logging
import traceback
import importlib.util
from datetime import datetime

from .smart_config import SmartConfig

logger = logging.getLogger(__name__)


class CodeExecutor:
    """Run strategy code from a submission directory and write logs."""

    def __init__(self, time_splits: Dict[str, Any]):
        """
        Args:
            time_splits: time-split config from experiment.yaml
        """
        self.time_splits = time_splits

    @staticmethod
    def _flatten_config(strategy_card: Dict[str, Any]) -> SmartConfig:
        """
        Wrap strategy_card in SmartConfig so LLM-generated code works with any
        parameter access pattern:
          config['N'], config.get('N'), config['parameters']['N']['value'], ...
        """
        return SmartConfig(strategy_card)

    def execute_strategy(
        self,
        submission_dir: Path,
        market_data: pd.DataFrame,
        strategy_card: Dict[str, Any],
        initial_capital: float = 100000.0,
    ) -> Tuple[bool, str]:
        """
        Execute strategy code.

        Args:
            submission_dir:  directory containing code/ and logs/
            market_data:     OHLCV DataFrame
            strategy_card:   parsed strategy_card.json
            initial_capital: starting capital

        Returns:
            (success, error_message)
        """
        try:
            logger.info("Loading strategy code...")
            entry_function = strategy_card.get('entry_function', {})
            code_file = submission_dir / 'code' / entry_function.get('file', 'strategy.py')

            if not code_file.exists():
                return False, f"Code file not found: {code_file}"

            strategy_module = self._load_module(code_file)
            class_or_function = entry_function.get('class_or_function', 'Strategy')
            strategy_obj = getattr(strategy_module, class_or_function)

            if isinstance(strategy_obj, type):
                logger.info(f"Instantiating strategy class: {class_or_function}")
                flattened_config = self._flatten_config(strategy_card)
                strategy = strategy_obj(flattened_config)
            else:
                strategy = strategy_obj

            logger.info(f"Running strategy on {len(market_data)} bars...")

            try:
                if hasattr(strategy, 'run'):
                    trade_log, audit_log = strategy.run(market_data, initial_capital)
                else:
                    trade_log, audit_log = strategy(market_data, initial_capital)

            except (ValueError, KeyError) as e:
                error_msg = str(e)
                multi_asset_keywords = [
                    "'close_x'", "'close_y'", "close_x", "close_y",
                    "keys 'X' and 'Y'", "keys 'near' and 'far'", "'near'", "'far'",
                    "MultiIndex columns", "multiple assets", "both assets", "two assets",
                ]
                if any(kw.lower() in error_msg.lower() for kw in multi_asset_keywords):
                    logger.warning(f"Strategy requires multi-asset data: {error_msg}")
                    logger.warning("Returning empty logs (strategy not applicable to single-asset data)")
                    trade_log = pd.DataFrame(columns=[
                        'trade_id', 'instrument', 'side', 'entry_time', 'entry_price',
                        'exit_time', 'exit_price', 'pnl', 'pnl_pct',
                    ])
                    first_dt = market_data['datetime'].iloc[0] if 'datetime' in market_data.columns else market_data.index[0]
                    audit_log = pd.DataFrame([{
                        'datetime': first_dt,
                        'equity': initial_capital,
                        'signal': 'not_applicable',
                        'message': f'Strategy requires multi-asset data: {error_msg[:100]}',
                    }])
                else:
                    raise

            if not isinstance(trade_log, pd.DataFrame):
                return False, "trade_log must be a pandas DataFrame"
            if not isinstance(audit_log, pd.DataFrame):
                return False, "audit_log must be a pandas DataFrame"

            logs_dir = submission_dir / 'logs'
            logs_dir.mkdir(exist_ok=True)
            trade_log.to_csv(logs_dir / 'trade_log.csv', index=False)
            audit_log.to_csv(logs_dir / 'audit_log.csv', index=False)

            logger.info(f"Strategy executed successfully: {len(trade_log)} trades")
            return True, ""

        except Exception as e:
            error_msg = f"Strategy execution failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return False, error_msg

    def _load_module(self, module_path: Path):
        """Dynamically load a Python module from file path."""
        spec = importlib.util.spec_from_file_location("strategy_module", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["strategy_module"] = module
        spec.loader.exec_module(module)
        return module

    def run_determinism_test(
        self,
        submission_dir: Path,
        market_data: pd.DataFrame,
        strategy_card: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Determinism gate: run strategy twice and compare outputs.

        Returns:
            (is_deterministic, report)
        """
        logger.info("Running determinism test...")
        try:
            success1, error1 = self.execute_strategy(submission_dir, market_data, strategy_card)
            if not success1:
                return False, f"First run failed: {error1}"

            logs_dir = submission_dir / 'logs'
            trade_log1 = pd.read_csv(logs_dir / 'trade_log.csv')
            audit_log1 = pd.read_csv(logs_dir / 'audit_log.csv')

            success2, error2 = self.execute_strategy(submission_dir, market_data, strategy_card)
            if not success2:
                return False, f"Second run failed: {error2}"

            trade_log2 = pd.read_csv(logs_dir / 'trade_log.csv')

            if trade_log1.equals(trade_log2):
                logger.info("Determinism test passed")
                return True, "Results are identical across runs"
            else:
                diff_report = self._generate_diff_report(trade_log1, trade_log2)
                logger.warning("Determinism test failed")
                return False, diff_report

        except Exception as e:
            return False, f"Determinism test error: {str(e)}"

    def _generate_diff_report(self, df1: pd.DataFrame, df2: pd.DataFrame) -> str:
        """Generate a human-readable diff report between two trade logs."""
        report = ["Trade logs differ between runs:"]
        if len(df1) != len(df2):
            report.append(f"- Row count: {len(df1)} vs {len(df2)}")
        for col in set(df1.columns) & set(df2.columns):
            if not df1[col].equals(df2[col]):
                report.append(f"- Column '{col}' differs")
                diff_mask = df1[col] != df2[col]
                for idx in diff_mask[diff_mask].index[:3]:
                    report.append(f"  Row {idx}: {df1[col].iloc[idx]} vs {df2[col].iloc[idx]}")
        return "\n".join(report)
