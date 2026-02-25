"""Data loader: load and preprocess market OHLCV data from CSV files."""
import pandas as pd
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DataLoader:
    """Load and manage market data per data_manifest.yaml."""

    def __init__(self, manifest_path: str, data_root: str = None):
        """
        Args:
            manifest_path: path to data_manifest.yaml
            data_root: override data root directory; falls back to manifest value
        """
        self.manifest_path = Path(manifest_path)
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            self.manifest = yaml.safe_load(f)

        if data_root is None:
            data_root = self.manifest.get('data_root', '../rawdata')

        self.data_root = Path(data_root)
        if not self.data_root.is_absolute():
            self.data_root = (self.manifest_path.parent.parent / self.data_root).resolve()

        logger.info(f"Data root: {self.data_root}")

    def load_market_data(
        self,
        market_id: str,
        symbol: str,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Load OHLCV data for a given market and symbol.

        Args:
            market_id: e.g. 'us_daily', 'crypto_1m'
            symbol:    ticker symbol
            time_min:  start time inclusive, 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'
            time_max:  end time exclusive
        Returns:
            DataFrame with columns [datetime, open, high, low, close, volume]
        """
        market_config = self.manifest['markets'].get(market_id)
        if not market_config:
            raise ValueError(f"Market {market_id} not found in manifest")

        if not market_config.get('enabled', True):
            raise ValueError(f"Market {market_id} is disabled")

        if 'derived_from' in market_config:
            return self._load_derived_data(market_id, symbol, time_min, time_max)

        instrument = next((i for i in market_config['instruments'] if i['symbol'] == symbol), None)
        if not instrument:
            raise ValueError(f"Symbol {symbol} not found in market {market_id}")

        csv_path = self.data_root / market_config['base_path'] / instrument['csv_file']
        if not csv_path.exists():
            raise FileNotFoundError(f"Data file not found: {csv_path}")

        df = pd.read_csv(csv_path)

        expected_cols = market_config['csv_format']['columns']
        if list(df.columns) != expected_cols:
            logger.warning(f"Column mismatch in {csv_path}. Expected {expected_cols}, got {list(df.columns)}")

        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
        df = df.drop_duplicates(subset='datetime', keep='first')

        if time_min:
            df = df[df['datetime'] >= pd.to_datetime(time_min)]
        if time_max:
            df = df[df['datetime'] < pd.to_datetime(time_max)]

        logger.info(f"Loaded {len(df)} bars for {symbol} from {market_id}")
        return df

    def _load_derived_data(
        self,
        market_id: str,
        symbol: str,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load derived (resampled) data; compute on the fly if not pre-saved."""
        market_config = self.manifest['markets'][market_id]
        csv_path = self.data_root / market_config['base_path'] / f"{symbol}.csv"

        if csv_path.exists():
            logger.info(f"Loading pre-computed derived data from {csv_path}")
            df = pd.read_csv(csv_path)
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.sort_values('datetime').reset_index(drop=True)
            if time_min:
                df = df[df['datetime'] >= pd.to_datetime(time_min)]
            if time_max:
                df = df[df['datetime'] < pd.to_datetime(time_max)]
            return df

        logger.info("Derived data not found, resampling from source...")
        source_market_id = market_config['derived_from']
        source_df = self.load_market_data(source_market_id, symbol, time_min, time_max)

        resample_config = market_config['resample_config']
        target_freq = resample_config['target_freq']
        source_df = source_df.set_index('datetime')
        agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        resampled = source_df.resample(target_freq).agg(agg_dict).dropna().reset_index()
        logger.info(f"Resampled {len(source_df)} -> {len(resampled)} bars ({target_freq})")
        return resampled

    def resample_and_save_all(self, market_id: str):
        """Resample all symbols for a derived market and save to disk."""
        market_config = self.manifest['markets'][market_id]
        if 'derived_from' not in market_config:
            raise ValueError(f"Market {market_id} is not a derived market")
        output_dir = self.data_root / market_config['base_path']
        output_dir.mkdir(parents=True, exist_ok=True)
        for inst in market_config['instruments']:
            symbol = inst['symbol']
            logger.info(f"Resampling {symbol}...")
            df = self._load_derived_data(market_id, symbol)
            output_path = output_dir / inst['csv_file']
            df.to_csv(output_path, index=False)
            logger.info(f"Saved to {output_path}")

    def get_available_symbols(self, market_id: str) -> List[str]:
        """Return all symbols available for a market."""
        market_config = self.manifest['markets'].get(market_id)
        if not market_config:
            return []
        return [inst['symbol'] for inst in market_config['instruments']]

    def get_time_range(self, market_id: str, symbol: str) -> Tuple[datetime, datetime]:
        """Return (min_datetime, max_datetime) for a symbol."""
        df = self.load_market_data(market_id, symbol)
        return df['datetime'].min(), df['datetime'].max()

    def validate_data_quality(self, df: pd.DataFrame) -> Dict[str, bool]:
        """Run basic data quality checks; return dict of check results."""
        checks = {}
        required_cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        checks['column_completeness'] = all(col in df.columns for col in required_cols)
        checks['datetime_sorted'] = df['datetime'].is_monotonic_increasing
        checks['no_duplicate_datetime'] = not df['datetime'].duplicated().any()
        checks['no_missing_ohlc'] = not df[['open', 'high', 'low', 'close']].isna().any().any()
        if checks['no_missing_ohlc']:
            checks['price_consistency'] = (
                (df['low'] <= df['open']).all() and
                (df['low'] <= df['close']).all() and
                (df['open'] <= df['high']).all() and
                (df['close'] <= df['high']).all()
            )
        else:
            checks['price_consistency'] = False
        return checks


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = DataLoader("../configs/data_manifest.yaml")
    df = loader.load_market_data("us_daily", "AAPL", "2025-01-01", "2026-01-01")
    print(f"Loaded {len(df)} bars for AAPL")
    print(df.head())
    print("Data quality:", loader.validate_data_quality(df))
