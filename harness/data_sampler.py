"""Data sampler: generate data format examples for LLM prompts."""
import pandas as pd
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class DataSampler:
    """Generate data format samples to include in LLM prompts."""

    def __init__(self, data_loader):
        self.data_loader = data_loader

    def generate_data_sample_prompt(
        self,
        market_id: str,
        symbol: str = None,
        num_rows: int = 10,
    ) -> str:
        """
        Build a formatted data sample text for the LLM prompt.

        Args:
            market_id: e.g. 'us_daily', 'crypto_1m'
            symbol:    if None, uses the first available symbol
            num_rows:  number of sample rows to show

        Returns:
            Formatted markdown string describing the data
        """
        try:
            if symbol is None:
                symbols = self.data_loader.get_available_symbols(market_id)
                if not symbols:
                    return f"No data available for market: {market_id}"
                symbol = symbols[0]

            df = self.data_loader.load_market_data(market_id, symbol)
            if len(df) == 0:
                return f"No data loaded for {market_id}/{symbol}"

            return self._format_sample(df, market_id, symbol, num_rows)

        except Exception as e:
            logger.error(f"Failed to generate data sample: {e}")
            return f"Error generating data sample: {str(e)}"

    def _format_sample(self, df: pd.DataFrame, market_id: str, symbol: str, num_rows: int) -> str:
        market_info = self._get_market_info(market_id)
        head_rows = min(num_rows // 2, len(df))
        tail_rows = min(num_rows - head_rows, len(df))

        return f"""
## Data Format and Sample

### Market Information
- Market ID: `{market_id}`
- Example Symbol: `{symbol}`
- Frequency: `{market_info.get('frequency', 'N/A')}`
- Timezone: `{market_info.get('timezone', 'N/A')}`
- Total Records: {len(df):,} bars
- Date Range: {df['datetime'].min()} to {df['datetime'].max()}

### Data Schema

| Column   | Type     | Description                     |
|----------|----------|---------------------------------|
| datetime | datetime | Bar timestamp (start of period) |
| open     | float    | Opening price                   |
| high     | float    | Highest price in period         |
| low      | float    | Lowest price in period          |
| close    | float    | Closing price                   |
| volume   | float    | Trading volume                  |

### Sample Data (First {head_rows} rows)

```
{df.head(head_rows).to_string(index=False)}
```

### Sample Data (Last {tail_rows} rows)

```
{df.tail(tail_rows).to_string(index=False)}
```

### Data Access in Your Code

```python
def run(self, market_data: pd.DataFrame, initial_capital: float):
    prices = market_data['close']
    for i in range(len(market_data)):
        row = market_data.iloc[i]
        current_price = row['close']
        current_time  = row['datetime']
        # your strategy logic here
```

### Important Notes

1. **No Future Data**: Only use data up to current bar `i` when making decisions at bar `i`
2. **Data Sorting**: Data is guaranteed to be sorted by datetime (ascending)
3. **No Missing Bars**: Data may have gaps (weekends, holidays)
4. **Datetime Format**: Timestamps are pandas datetime64[ns] objects
"""

    def _get_market_info(self, market_id: str) -> Dict[str, Any]:
        markets = self.data_loader.manifest.get('markets', {})
        if market_id in markets:
            mc = markets[market_id]
            return {'frequency': mc.get('frequency', 'N/A'), 'timezone': mc.get('timezone', 'N/A')}
        return {}

    def generate_multi_market_sample(self, market_ids: List[str], num_rows: int = 5) -> str:
        """Generate samples for multiple markets and concatenate."""
        samples = [self.generate_data_sample_prompt(m, num_rows=num_rows) for m in market_ids]
        return "\n\n" + ("=" * 80 + "\n\n").join(samples)
