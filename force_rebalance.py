#!/usr/bin/env python3
"""
Force immediate rebalance for a specific strategy
Usage: python force_rebalance.py <strategy_name>
Example: python force_rebalance.py vol_regime_weekly
"""

import os
import sys
import logging
import yaml
from datetime import datetime
from importlib import import_module

from shared.alpaca_broker import AlpacaBroker
from shared.data_provider import DataProvider

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def load_config():
    """Load strategy configuration from YAML"""
    config_path = 'config/strategies.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def force_rebalance(strategy_name: str):
    """Force a rebalance for the specified strategy"""
    logger.info(f"Forcing rebalance for: {strategy_name}")

    # Load config
    config = load_config()
    strategy_config = next(
        (s for s in config['strategies'] if s['name'] == strategy_name),
        None
    )

    if not strategy_config:
        logger.error(f"Strategy '{strategy_name}' not found in config")
        return False

    try:
        # Create broker
        account = strategy_config['account']
        api_key = os.getenv(account['api_key_env'])
        secret_key = os.getenv(account['secret_key_env'])
        paper = os.getenv(account.get('paper_env', 'PAPER_TRADING'), 'true').lower() == 'true'

        broker = AlpacaBroker(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
            strategy_name=strategy_config['name']
        )

        # Create data provider
        data_provider = DataProvider(api_key, secret_key)

        # Create strategy
        module = import_module(strategy_config['module'])
        strategy_class = getattr(module, strategy_config['class'])
        rebalance_frequency = strategy_config.get('rebalance_frequency', 'monthly')
        strategy = strategy_class(broker, data_provider, rebalance_frequency=rebalance_frequency)

        # Initialize
        logger.info("Initializing strategy...")
        strategy.initialize()

        # Force execute (bypassing should_rebalance_today check)
        logger.info("=" * 70)
        logger.info(f"FORCING REBALANCE: {strategy.name}")
        logger.info("=" * 70)

        signals = strategy.calculate_signals()

        if signals:
            strategy.execute_trades(signals)
            logger.info(f"✓ Rebalance completed: {signals}")
            return True
        else:
            logger.warning("No signals generated")
            return False

    except Exception as e:
        logger.error(f"Force rebalance failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python force_rebalance.py <strategy_name>")
        print("\nAvailable strategies:")
        config = load_config()
        for s in config['strategies']:
            print(f"  - {s['name']}")
        sys.exit(1)

    strategy_name = sys.argv[1]
    success = force_rebalance(strategy_name)
    sys.exit(0 if success else 1)
