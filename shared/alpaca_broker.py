# shared/alpaca_broker.py
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.data.enums import DataFeed
import logging
from typing import Optional


class AlpacaBroker:
    """
    Alpaca trading interface - one instance per account
    """

    def __init__(self, api_key: str, secret_key: str, paper: bool = True, strategy_name: str = "Strategy"):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.strategy_name = strategy_name
        self.logger = logging.getLogger(f"Broker-{strategy_name}")

        # Initialize clients
        self.trading_client = TradingClient(api_key, secret_key, paper=paper)
        self.data_client = StockHistoricalDataClient(api_key, secret_key)

        # Verify connection
        try:
            account = self.get_account()
            account_type = "Paper" if paper else "Live"
            self.logger.info(
                f"Connected to Alpaca ({account_type}) - "
                f"Equity: ${float(account.equity):,.2f}"
            )
        except Exception as e:
            self.logger.error(f"Failed to connect to Alpaca: {e}")
            raise

    def get_account(self):
        """Get account information"""
        return self.trading_client.get_account()

    def get_positions(self):
        """Get all current positions"""
        try:
            return self.trading_client.get_all_positions()
        except:
            return []

    def get_position(self, symbol: str):
        """Get specific position"""
        try:
            return self.trading_client.get_open_position(symbol)
        except:
            return None

    def liquidate_all(self):
        """Close all positions"""
        try:
            self.trading_client.close_all_positions(cancel_orders=True)
            self.logger.info("All positions liquidated")
        except Exception as e:
            self.logger.error(f"Liquidation error: {e}")
            raise

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current ask price using IEX feed (free with Basic tier)
        """
        try:
            request = StockLatestQuoteRequest(
                symbol_or_symbols=symbol,
                feed=DataFeed.IEX  # ← Add this
            )
            quote = self.data_client.get_stock_latest_quote(request)
            return float(quote[symbol].ask_price)
        except Exception as e:
            self.logger.error(f"Failed to get price for {symbol}: {e}")
            return None

    def set_holdings(self, symbol: str, target_weight: float):
        """
        Set position to target weight of portfolio
        target_weight: 0.0 to 1.0 (e.g., 0.5 = 50%)
        """
        account = self.get_account()
        equity = float(account.equity)
        target_value = equity * target_weight

        current_price = self.get_current_price(symbol)

        if current_price is None or current_price <= 0:
            self.logger.error(f"Invalid price for {symbol}, skipping order")
            return None

        qty = int(target_value / current_price)

        if qty > 0:
            try:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                order = self.trading_client.submit_order(order_data)
                self.logger.info(
                    f"Order placed: {qty} shares of {symbol} "
                    f"@ ${current_price:.2f} = ${qty * current_price:,.2f}"
                )
                return order
            except Exception as e:
                self.logger.error(f"Order failed for {symbol}: {e}")
                raise
        else:
            self.logger.warning(
                f"Calculated qty=0 for {symbol} "
                f"(price: ${current_price:.2f}, target: ${target_value:.2f})"
            )
            return None