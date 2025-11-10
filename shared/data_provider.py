# shared/data_provider.py - UPDATED VERSION

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed  # ← Add this import
from datetime import datetime, timedelta
import pandas as pd
import logging


class DataProvider:
    """
    Fetch historical and real-time market data
    Shared across all strategies to minimize API calls
    """

    def __init__(self, api_key: str, secret_key: str):
        self.client = StockHistoricalDataClient(api_key, secret_key)
        self.logger = logging.getLogger("DataProvider")

    def get_historical_bars(self, symbol: str, days: int, timeframe: TimeFrame = TimeFrame.Day) -> pd.DataFrame:
        """
        Fetch historical bars using IEX feed (free with Basic tier)
        Returns DataFrame with columns: open, high, low, close, volume
        """
        try:
            end = datetime.now()
            start = end - timedelta(days=days + 10)  # Buffer for weekends

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                feed=DataFeed.IEX  # ← KEY CHANGE: Use IEX instead of SIP
            )

            bars = self.client.get_stock_bars(request)
            df = bars.df

            # Handle multi-index if present
            if isinstance(df.index, pd.MultiIndex):
                if symbol in df.index.get_level_values(0):
                    df = df.xs(symbol, level=0)

            self.logger.info(f"Fetched {len(df)} bars for {symbol} (IEX feed)")
            return df

        except Exception as e:
            self.logger.error(f"Failed to fetch bars for {symbol}: {e}")
            return pd.DataFrame()