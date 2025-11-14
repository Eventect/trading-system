# strategies/base_strategy.py
from abc import ABC, abstractmethod
from datetime import datetime
import logging
import json
import os
from typing import Dict, Optional
import time


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies
    Handles state persistence and execution logic
    """

    def __init__(self, name: str, broker, data_provider):
        self.name = name
        self.broker = broker
        self.data_provider = data_provider
        self.logger = logging.getLogger(name)
        self.is_initialized = False

        # State directory - works locally and on Render
        self.state_dir = os.getenv('STATE_DIR', './data')  # ← Key change
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, f'{name}_state.json')

        self.logger.info(f"State directory: {self.state_dir}")
        
    @abstractmethod
    def initialize(self):
        """Initialize strategy - fetch historical data"""
        pass

    @abstractmethod
    def should_rebalance_today(self) -> bool:
        """
        Check if rebalancing is needed today
        Called once per day when market conditions are met
        """
        pass

    @abstractmethod
    def calculate_signals(self) -> Dict[str, float]:
        """
        Calculate trading signals
        Returns: dict {symbol: target_weight}
        """
        pass

    def load_state(self) -> Optional[dict]:
        """Load persisted state from file"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                self.logger.info(f"State restored from {self.state_file}")
                return state
            except Exception as e:
                self.logger.warning(f"Failed to load state: {e}")
                return None
        return None

    def save_state(self, state_data: dict):
        """Persist state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2, default=str)
            self.logger.info(f"State saved to {self.state_file}")
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")

    def execute(self) -> bool:
        """
        Main execution method
        Returns: True if rebalanced, False if skipped
        """
        try:
            if not self.is_initialized:
                self.logger.warning("Strategy not initialized, skipping execution")
                return False

            if not self.should_rebalance_today():
                self.logger.debug("No rebalancing needed today")
                return False

            self.logger.info("=" * 60)
            self.logger.info(f"EXECUTING REBALANCE: {self.name}")
            self.logger.info("=" * 60)

            signals = self.calculate_signals()

            if signals:
                self.execute_trades(signals)
                self.logger.info(f"✓ Rebalance completed: {signals}")
                return True
            else:
                self.logger.info("No signals generated, skipping trades")
                return False

        except Exception as e:
            self.logger.error(f"Execution failed: {e}", exc_info=True)
            return False

    def execute_trades(self, target_allocation: Dict[str, float]):
        """Execute trades to reach target allocation"""
        # Liquidate current positions
        self.broker.liquidate_all()

        # Add brief delay to ensure liquidation is fully processed
        # Prevents Alpaca wash trade detection when re-entering same symbols
        time.sleep(1)

        # Enter new positions
        for symbol, weight in target_allocation.items():
            if weight > 0:
                self.broker.set_holdings(symbol, weight)