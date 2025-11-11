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

    def __init__(self, api_key: str, secret_key: str, paper: bool = True,
                 strategy_name: str = "Strategy", use_fractional: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.strategy_name = strategy_name
        self.use_fractional = use_fractional  # ← NEW
        self.logger = logging.getLogger(f"Broker-{strategy_name}")

        # Initialize clients
        self.trading_client = TradingClient(api_key, secret_key, paper=paper)
        self.data_client = StockHistoricalDataClient(api_key, secret_key)

        # Verify connection
        try:
            account = self.get_account()
            account_type = "Paper" if paper else "Live"
            fractional_status = "with fractional shares" if use_fractional else "whole shares only"
            self.logger.info(
                f"Connected to Alpaca ({account_type}) - "
                f"Equity: ${float(account.equity):,.2f} - "
                f"Using IEX feed (Basic tier) - {fractional_status}"
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
        Supports fractional shares for better capital utilization
        
        Args:
            symbol: Stock symbol
            target_weight: 0.0 to 1.0 (e.g., 0.5 = 50% of portfolio)
        """
        account = self.get_account()
        equity = float(account.equity)
        target_value = equity * target_weight

        current_price = self.get_current_price(symbol)

        if current_price is None or current_price <= 0:
            self.logger.error(f"Invalid price for {symbol}, skipping order")
            return

        if self.use_fractional:
            # Use notional (dollar amount) order - Alpaca handles fractional shares
            self._place_notional_order(symbol, target_value)
        else:
            # Use traditional quantity order (whole shares only)
            self._place_quantity_order(symbol, target_value, current_price)

    def _place_notional_order(self, symbol: str, target_value: float):
        """
        Place order by dollar amount (supports fractional shares)
        This uses ALL available capital efficiently
        """
        if target_value < 1.0:
            self.logger.warning(f"Target value ${target_value:.2f} too small for {symbol}")
            return

        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            order_data = MarketOrderRequest(
                symbol=symbol,
                notional=round(target_value, 2),  # ← Order by dollar amount
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY
            )

            order = self.trading_client.submit_order(order_data)
            self.logger.info(
                f"Order placed: ${target_value:,.2f} of {symbol} (fractional shares enabled)"
            )
            return order

        except Exception as e:
            self.logger.error(f"Fractional order failed for {symbol}: {e}")
            self.logger.info("Falling back to whole shares...")
            # Fallback to whole shares
            current_price = self.get_current_price(symbol)
            if current_price:
                self._place_quantity_order(symbol, target_value, current_price)

    def _place_quantity_order(self, symbol: str, target_value: float, current_price: float):
        """
        Place order by quantity (whole shares only)
        Leaves some cash unused for expensive securities
        """
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

                actual_value = qty * current_price
                unused_cash = target_value - actual_value

                self.logger.info(
                    f"Order placed: {qty} shares of {symbol} @ ${current_price:.2f} = ${actual_value:,.2f} "
                    f"(${unused_cash:.2f} cash unused)"
                )
                return order

            except Exception as e:
                self.logger.error(f"Order failed: {e}")
                raise
        else:
            self.logger.warning(
                f"Calculated qty=0 for {symbol} "
                f"(price: ${current_price:.2f}, target: ${target_value:.2f})"
            )