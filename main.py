# main.py
import os
import time
import logging
from datetime import datetime, timedelta
import yaml
from importlib import import_module

from shared.alpaca_broker import AlpacaBroker
from shared.data_provider import DataProvider
from shared.market_calendar import MarketCalendar
from shared.email_logger import EmailLogger

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/data/trading.log')
    ]
)
logger = logging.getLogger(__name__)


def load_config():
    """Load strategy configuration from YAML"""
    config_path = 'config/strategies.yaml'
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def create_broker(strategy_config):
    """Create Alpaca broker instance from config"""
    account = strategy_config['account']

    api_key = os.getenv(account['api_key_env'])
    secret_key = os.getenv(account['secret_key_env'])
    paper = os.getenv(account.get('paper_env', 'PAPER_TRADING'), 'true').lower() == 'true'

    if not api_key or not secret_key:
        raise ValueError(f"Missing credentials for {strategy_config['name']}")

    return AlpacaBroker(
        api_key=api_key,
        secret_key=secret_key,
        paper=paper,
        strategy_name=strategy_config['name']
    )


def create_strategy(strategy_config, broker, data_provider):
    """Create strategy instance from config"""
    module = import_module(strategy_config['module'])
    strategy_class = getattr(module, strategy_config['class'])
    return strategy_class(broker, data_provider)


def main():
    """Main trading system orchestrator"""
    logger.info("=" * 70)
    logger.info("STARTING MULTI-STRATEGY TRADING SYSTEM")
    logger.info("=" * 70)

    # Initialize market calendar (handles timezones)
    market_calendar = MarketCalendar()
    logger.info(f"Server time: {datetime.now()}")
    logger.info(f"Market time (ET): {market_calendar.get_market_time()}")

    # Initialize email logger
    email_logger = EmailLogger()

    # Load configuration
    config = load_config()
    strategies_config = [s for s in config['strategies'] if s.get('enabled', False)]
    logger.info(f"Loaded {len(strategies_config)} enabled strategies")

    # Create shared data provider (uses any Alpaca credentials)
    first_strategy = strategies_config[0]
    data_api_key = os.getenv(first_strategy['account']['api_key_env'])
    data_secret_key = os.getenv(first_strategy['account']['secret_key_env'])
    data_provider = DataProvider(data_api_key, data_secret_key)

    # Initialize strategies
    strategies = []
    for config_item in strategies_config:
        try:
            broker = create_broker(config_item)
            strategy = create_strategy(config_item, broker, data_provider)
            strategy.initialize()
            strategies.append(strategy)
            logger.info(f"✓ {strategy.name} initialized successfully")
            email_logger.add_log(f"✓ {strategy.name} initialized")
        except Exception as e:
            logger.error(f"✗ {config_item['name']} initialization failed: {e}")
            email_logger.add_log(f"✗ {config_item['name']} failed: {e}")

    if not strategies:
        logger.error("No strategies loaded. Exiting.")
        return

    logger.info("=" * 70)
    logger.info(f"{len(strategies)} strategies ready")
    logger.info("Checking for rebalancing opportunities every minute...")
    logger.info("Target execution time: 3:30 PM ET (month-end)")
    logger.info("=" * 70)

    # Track last execution date for daily email
    last_email_date = None

    # Main loop - check every minute
    iteration = 0
    while True:
        try:
            iteration += 1
            market_time = market_calendar.get_market_time()

            # Heartbeat every 30 minutes
            if iteration % 30 == 1:
                logger.info(
                    f"[Heartbeat] Market time: {market_time.strftime('%Y-%m-%d %H:%M:%S %Z')} | "
                    f"{len(strategies)} strategies active"
                )

            # Check if it's time to execute (3:30 PM ET on trading days)
            if market_calendar.is_time_to_rebalance():
                logger.info("=" * 70)
                logger.info(f"REBALANCE CHECK: {market_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                logger.info("=" * 70)

                for strategy in strategies:
                    try:
                        executed = strategy.execute()
                        if executed:
                            email_logger.add_log(f"{strategy.name}: Rebalanced successfully")
                        else:
                            email_logger.add_log(f"{strategy.name}: No rebalance needed")
                    except Exception as e:
                        logger.error(f"Strategy {strategy.name} error: {e}", exc_info=True)
                        email_logger.add_log(f"{strategy.name}: ERROR - {e}")

            # Send daily email at 5 PM ET
            if market_time.hour == 17 and market_time.minute == 0:
                today = market_time.date()
                if last_email_date != today:
                    email_logger.send_daily_summary()
                    last_email_date = today

            # Sleep until next minute
            time.sleep(market_calendar.time_until_next_check())

        except KeyboardInterrupt:
            logger.info("Shutting down trading system...")
            email_logger.send_daily_summary(subject="Trading System Shutdown")
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            time.sleep(60)


if __name__ == "__main__":
    main()