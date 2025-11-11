# force_test_rebalance.py
"""
One-time test script to force a rebalance for testing
Run this once to verify everything works, then delete it

Usage:
    python force_test_rebalance.py --strategy monthly
    python force_test_rebalance.py --strategy weekly
"""

import os
import sys
import logging
from datetime import datetime

# Load environment (for local testing)
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # Not needed on Render

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from shared.alpaca_broker import AlpacaBroker
from shared.data_provider import DataProvider
from strategies.volatility_regime import VolatilityRegimeStrategy


def force_test_rebalance(strategy_frequency="monthly"):
    """Force a single test rebalance to verify system works"""
    logger.info("=" * 70)
    logger.info("FORCING TEST REBALANCE")
    logger.info(f"Strategy: {strategy_frequency}")
    logger.info("=" * 70)

    # Determine which environment variables to use
    if strategy_frequency == "monthly":
        env_prefix = "ALPACA_VOL_MONTHLY"
    elif strategy_frequency == "weekly":
        env_prefix = "ALPACA_VOL_WEEKLY"
    else:
        env_prefix = "ALPACA_VOL_MONTHLY"  # Default

    # Get credentials
    api_key = os.getenv(f'{env_prefix}_API_KEY')
    secret_key = os.getenv(f'{env_prefix}_SECRET_KEY')
    paper = os.getenv(f'{env_prefix}_PAPER', 'true').lower() == 'true'

    if not api_key or not secret_key:
        logger.error(f"Missing credentials! Looking for: {env_prefix}_API_KEY and {env_prefix}_SECRET_KEY")
        logger.error("Available env vars: " + ", ".join([k for k in os.environ.keys() if 'ALPACA' in k]))
        return False

    try:
        # Create broker and data provider
        logger.info(f"Connecting to Alpaca ({'Paper' if paper else 'Live'})...")
        broker = AlpacaBroker(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
            strategy_name=f"TestRebalance-{strategy_frequency}"
        )

        data_provider = DataProvider(api_key, secret_key)

        # Create strategy
        logger.info(f"Creating {strategy_frequency} strategy...")
        strategy = VolatilityRegimeStrategy(
            broker=broker,
            data_provider=data_provider,
            rebalance_frequency=strategy_frequency
        )

        # Initialize
        logger.info("Initializing strategy...")
        strategy.initialize()

        # Display current state
        logger.info("=" * 70)
        logger.info("CURRENT STATE:")
        logger.info(f"  Volatility: {strategy.current_volatility:.1%}")
        logger.info(f"  Regime: {strategy.get_current_regime()}")
        logger.info(f"  Last Rebalance: {strategy.last_rebalance_date}")
        logger.info(f"  Trade Count: {strategy.trade_count}")

        # Check current positions
        positions = broker.get_positions()
        logger.info(f"  Current Positions: {len(positions)}")
        for pos in positions:
            logger.info(
                f"    - {pos.symbol}: {pos.qty} shares @ ${float(pos.current_price):.2f} = ${float(pos.market_value):,.2f}")

        account = broker.get_account()
        logger.info(f"  Account Equity: ${float(account.equity):,.2f}")
        logger.info(f"  Buying Power: ${float(account.buying_power):,.2f}")
        logger.info("=" * 70)

        # Ask for confirmation
        print("\n⚠️  WARNING: This will execute a REAL trade in your paper account!")
        print("=" * 70)
        confirm = input("\nType 'YES' to proceed with test rebalance: ")

        if confirm != 'YES':
            logger.info("Test cancelled by user")
            return False

        # Calculate signals
        logger.info("\nCalculating signals...")
        signals = strategy.calculate_signals()
        logger.info(f"Signals: {signals}")

        if not signals:
            logger.warning("No signals generated! Strategy may not want to trade right now.")
            return False

        # Execute trades
        logger.info("\nExecuting trades...")
        strategy.execute_trades(signals)

        # Wait for orders to fill
        logger.info("\nWaiting 5 seconds for orders to fill...")
        import time
        time.sleep(5)

        # Check new positions
        positions = broker.get_positions()
        account = broker.get_account()

        logger.info("=" * 70)
        logger.info("NEW STATE:")
        logger.info(f"  Account Equity: ${float(account.equity):,.2f}")
        logger.info(f"  Positions: {len(positions)}")
        for pos in positions:
            logger.info(
                f"    - {pos.symbol}: {pos.qty} shares @ ${float(pos.current_price):.2f} = ${float(pos.market_value):,.2f}")
        logger.info("=" * 70)

        logger.info("\n✓ TEST REBALANCE COMPLETED!")
        logger.info("\nNext steps:")
        logger.info("1. Check your Alpaca paper account at https://app.alpaca.markets")
        logger.info("2. Verify the position looks correct")
        logger.info("3. Check Render logs to see if normal operation continues correctly")
        logger.info("4. Delete this script: git rm force_test_rebalance.py")

        return True

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Force a test rebalance to verify system works')
    parser.add_argument('--strategy',
                        default='monthly',
                        choices=['monthly', 'weekly', 'daily', 'adaptive'],
                        help='Strategy frequency to test (default: monthly)')
    args = parser.parse_args()

    success = force_test_rebalance(args.strategy)
    sys.exit(0 if success else 1)