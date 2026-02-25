#!/usr/bin/env python3
"""
Sample run: load config + data, run one strategy, write logs.
Run from repo root:  python github/run_sample.py
Or from folder:      cd github && python run_sample.py
Logs are written to submission/logs/ and are committed in this repo.
"""
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import yaml
from harness import DataLoader, CodeExecutor


def main():
    config_dir = ROOT / "configs"
    with open(config_dir / "experiment.yaml", "r", encoding="utf-8") as f:
        experiment = yaml.safe_load(f)
    with open(config_dir / "data_manifest.yaml", "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    data_root = manifest.get("data_root", "./sample_data")
    if not (ROOT / data_root).is_absolute():
        data_root = str(ROOT / data_root)

    loader = DataLoader(str(config_dir / "data_manifest.yaml"), data_root=data_root)
    executor = CodeExecutor(experiment["time_splits"])

    market_id = "us_daily"
    symbol = "AAPL"
    time_min = "2024-01-01"
    time_max = "2025-12-31"

    print("Loading data...")
    df = loader.load_market_data(market_id, symbol, time_min, time_max)
    print(f"  Loaded {len(df)} bars for {symbol}")

    submission_dir = ROOT / "submission"
    with open(submission_dir / "strategy_card.json", "r", encoding="utf-8") as f:
        strategy_card = json.load(f)

    print("Running strategy...")
    success, err = executor.execute_strategy(submission_dir, df, strategy_card, initial_capital=100000.0)
    if not success:
        print("  ERROR:", err)
        return 1

    trade_log_path = submission_dir / "logs" / "trade_log.csv"
    audit_log_path = submission_dir / "logs" / "audit_log.csv"
    print(f"  Success. Logs written to submission/logs/ (trade_log.csv, audit_log.csv)")

    if trade_log_path.exists():
        import pandas as pd
        trades = pd.read_csv(trade_log_path)
        print(f"\n  Number of trades: {len(trades)}")
        if len(trades) > 0:
            print(trades[["entry_time", "entry_price", "exit_time", "exit_price", "pnl", "pnl_pct"]].to_string())
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
