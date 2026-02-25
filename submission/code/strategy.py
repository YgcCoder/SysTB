"""
Bollinger Band mean-reversion strategy (SysTradeBench sample).
Expects: config with N, k, stop_loss_pct; run(ohlcv_df, initial_capital) -> (trade_log_df, audit_log_df).
"""
import pandas as pd
import numpy as np


class Strategy:
    def __init__(self, config):
        self.config = config
        self.N = int(config.get("N", 20))
        self.k = float(config.get("k", 2.0))
        self.stop_loss_pct = float(config.get("stop_loss_pct", 0.10))

    def run(self, market_data: pd.DataFrame, initial_capital: float = 100000.0):
        df = market_data.copy()
        df = df.sort_values("datetime").reset_index(drop=True)
        n = len(df)
        if n < self.N + 1:
            trade_log = pd.DataFrame(
                columns=["trade_id", "instrument", "side", "entry_time", "entry_price", "exit_time", "exit_price", "pnl", "pnl_pct"]
            )
            audit_log = pd.DataFrame({"datetime": df["datetime"], "close": df["close"], "equity": [initial_capital] * n, "signal": "none", "position_state": "flat"})
            return trade_log, audit_log

        close = df["close"].values
        mb = pd.Series(close).rolling(self.N).mean().values
        std = pd.Series(close).rolling(self.N).std().values
        ub = mb + self.k * np.where(np.isfinite(std), std, 0)
        lb = mb - self.k * np.where(np.isfinite(std), std, 0)

        position = 0
        entry_price = 0.0
        entry_time = None
        equity = initial_capital
        trades = []
        audit_rows = []

        for i in range(self.N, n):
            dt = df["datetime"].iloc[i]
            c = close[i]
            m, u, l = mb[i], ub[i], lb[i]
            sig = "none"
            if not np.isfinite(m) or not np.isfinite(l):
                audit_rows.append({"datetime": dt, "close": c, "MB": m, "UB": u, "LB": l, "signal": sig, "position_state": "flat" if position == 0 else "long", "equity": equity})
                continue

            if position == 0:
                if c < l and close[i - 1] >= lb[i - 1]:
                    position = 1
                    entry_price = c
                    entry_time = dt
                    sig = "enter"
            else:
                if c <= entry_price * (1 - self.stop_loss_pct):
                    pnl = (c - entry_price) * (initial_capital / entry_price)
                    equity += pnl
                    trades.append({"trade_id": len(trades) + 1, "instrument": "symbol", "side": "long", "entry_time": entry_time, "entry_price": entry_price, "exit_time": dt, "exit_price": c, "pnl": pnl, "pnl_pct": (c - entry_price) / entry_price * 100})
                    position = 0
                    sig = "exit_stop"
                elif c >= m:
                    pnl = (c - entry_price) * (initial_capital / entry_price)
                    equity += pnl
                    trades.append({"trade_id": len(trades) + 1, "instrument": "symbol", "side": "long", "entry_time": entry_time, "entry_price": entry_price, "exit_time": dt, "exit_price": c, "pnl": pnl, "pnl_pct": (c - entry_price) / entry_price * 100})
                    position = 0
                    sig = "exit_mb"

            audit_rows.append({"datetime": dt, "close": c, "MB": m, "UB": u, "LB": l, "signal": sig, "position_state": "flat" if position == 0 else "long", "equity": equity})

        trade_log = pd.DataFrame(trades) if trades else pd.DataFrame(columns=["trade_id", "instrument", "side", "entry_time", "entry_price", "exit_time", "exit_price", "pnl", "pnl_pct"])
        audit_log = pd.DataFrame(audit_rows)
        return trade_log, audit_log
