# Crypto 1-Minute Data

This folder contains a **1-month sample** (January 2024) of 1-minute OHLCV bars for BTC/USDT, ETH/USDT, and BNB/USDT, for quick local testing.

| File | Period | Rows |
|------|--------|------|
| `BTCUSDT_1min_sample.csv` | 2024-01-01 ~ 2024-02-01 | 44,641 |
| `ETHUSDT_1min_sample.csv` | 2024-01-01 ~ 2024-02-01 | 44,641 |
| `BNBUSDT_1min_sample.csv` | 2024-01-01 ~ 2024-02-01 | 44,641 |

Columns: `datetime, open, high, low, close, volume`

---

## Download Full 1-Min Data (2024–2025)

The paper's intraday strategies (Dual Thrust, R-Breaker) use the full 2-year dataset (~525K rows/asset).  
Download directly from **Binance Data Vision** (no account required):

**[https://data.binance.vision/?prefix=data/spot/monthly/klines/](https://data.binance.vision/?prefix=data/spot/monthly/klines/)**

Steps:
1. Navigate to `data/spot/monthly/klines/BTCUSDT/1m/` (repeat for ETHUSDT, BNBUSDT)
2. Download monthly ZIP files for **2024-01** through **2025-12**
3. Unzip and concatenate into a single CSV per pair
4. Place files as `data/crypto_1min/BTCUSDT_1min.csv` etc.
5. Update `crypto_1min_dir` in `configs/data_manifest.yaml`

Column order in Binance files:  
`open_time, open, high, low, close, volume, close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore`  
→ Keep only `open_time, open, high, low, close, volume` and rename `open_time` to `datetime`.
