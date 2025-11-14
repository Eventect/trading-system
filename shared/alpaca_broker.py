# shared/alpaca_broker.py
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.data.enums import DataFeed
import logging
from typing import Optional
import time


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

    def get_portfolio_weights(self) -> dict:
        """
        Get current portfolio allocation as weights (0.0 to 1.0)
        Returns: {symbol: weight, ...}
        Example: {'UPRO': 1.0} or {'SPY': 0.6, 'SH': 0.4}
        """
        try:
            positions = self.get_positions()
            account = self.get_account()
            equity = float(account.equity)

            if not positions or equity <= 0:
                return {}

            weights = {}
            for pos in positions:
                symbol = pos.symbol
                position_value = float(pos.market_value)
                weight = position_value / equity
                if weight > 0.001:  # Only include positions > 0.1%
                    weights[symbol] = weight

            return weights

        except Exception as e:
            self.logger.error(f"Failed to get portfolio weights: {e}")
            return {}

    def liquidate_position(self, symbol: str):
        """Close a specific position"""
        try:
            position = self.get_position(symbol)
            if not position:
                self.logger.debug(f"No position to liquidate for {symbol}")
                return

            self.trading_client.close_position(symbol)
            self.logger.info(f"Liquidated {symbol}")

            # Wait for order to complete
            self._wait_for_position_closure(symbols=[symbol])

        except Exception as e:
            self.logger.error(f"Failed to liquidate {symbol}: {e}")
            raise

    def liquidate_all(self):
        """Close all positions and wait for orders to complete"""
        try:
            self.trading_client.close_all_positions(cancel_orders=True)
            self.logger.info("Liquidation initiated, waiting for orders to complete...")

            # Wait for all liquidation orders to complete to avoid wash trade detection
            self._wait_for_position_closure()

            self.logger.info("All positions liquidated and orders completed")
        except Exception as e:
            self.logger.error(f"Liquidation error: {e}")
            raise

    def _wait_for_position_closure(self, symbols: list = None, max_wait_seconds: int = 30, check_interval: float = 0.5):
        """
        Wait for liquidation orders to complete
        Prevents wash trade detection by ensuring positions are fully closed
        before placing new orders

        Args:
            symbols: List of symbols to wait for closure. If None, waits for all positions.
            max_wait_seconds: Max time to wait before timeout
            check_interval: How often to check position status
        """
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            try:
                positions = self.get_positions()
                current_symbols = {pos.symbol for pos in positions}

                # Determine what we're waiting for
                if symbols is None:
                    # Waiting for all positions to close
                    if not positions:
                        self.logger.info("All positions closed successfully")
                        return
                else:
                    # Waiting for specific symbols to close
                    remaining = current_symbols & set(symbols)
                    if not remaining:
                        self.logger.info(f"Positions closed for {symbols}")
                        return

                time.sleep(check_interval)

            except Exception as e:
                self.logger.warning(f"Error checking positions: {e}")
                time.sleep(check_interval)

        # Timeout - log warning but continue
        remaining_positions = self.get_positions()
        if remaining_positions:
            self.logger.warning(
                f"Timeout waiting for position closure. Still have {len(remaining_positions)} positions. "
                f"Proceeding anyway, but wash trade errors may occur."
            )

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