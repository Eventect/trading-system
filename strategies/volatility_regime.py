# strategies/volatility_regime.py
from strategies.base_strategy import BaseStrategy
from collections import deque
from datetime import datetime, timedelta
import numpy as np
import calendar


class VolatilityRegimeStrategy(BaseStrategy):
    """
    Volatility Regime Strategy v4.5 - Configurable Rebalancing Frequency

    Supports multiple rebalancing frequencies:
    - 'daily': Rebalance when regime changes (max once per day)
    - 'weekly': Rebalance every Friday
    - 'monthly': Rebalance at month-end (original)
    - 'adaptive': Rebalance on regime change OR weekly safety check
    """

    def __init__(self, broker, data_provider, rebalance_frequency='monthly'):
        super().__init__(f"VolRegime-{rebalance_frequency}", broker, data_provider)

        # Validate frequency
        valid_frequencies = ['daily', 'weekly', 'monthly', 'adaptive']
        if rebalance_frequency not in valid_frequencies:
            raise ValueError(f"Invalid frequency. Must be one of: {valid_frequencies}")

        self.rebalance_frequency = rebalance_frequency

        # Parameters
        self.vol_lookback = 20
        self.vol_low_threshold = 0.15  # Below 15% = UPRO
        self.vol_high_threshold = 0.25  # Above 25% = SH
        self.vix_panic_threshold = 30

        # Recovery mode tracking
        self.in_recovery_mode = False
        self.recovery_mode_start = None
        self.max_recovery_days = 45
        self.vix_recovery_threshold = 20

        # Data storage
        self.spy_prices = deque(maxlen=self.vol_lookback + 1)
        self.current_vix = None
        self.current_volatility = None

        # State tracking
        self.last_rebalance_date = None
        self.last_regime = None
        self.trade_count = 0

        self.logger.info(f"Strategy configured with '{rebalance_frequency}' rebalancing")

    def initialize(self):
        """
        Initialize strategy - fetch historical data
        NO WARMUP TIME - fetches all data immediately
        """
        self.logger.info(f"Initializing Volatility Regime Strategy ({self.rebalance_frequency})...")

        # Try to restore state
        state = self.load_state()
        if state:
            if state.get('last_rebalance_date'):
                self.last_rebalance_date = datetime.fromisoformat(state['last_rebalance_date'])
            self.last_regime = state.get('last_regime')
            self.trade_count = state.get('trade_count', 0)
            self.in_recovery_mode = state.get('in_recovery_mode', False)
            if state.get('recovery_mode_start'):
                self.recovery_mode_start = datetime.fromisoformat(state['recovery_mode_start'])

            self.logger.info(
                f"State restored - Last rebalance: {self.last_rebalance_date}, Last regime: {self.last_regime}")

        # Fetch historical SPY data
        spy_df = self.data_provider.get_historical_bars('SPY', self.vol_lookback + 5)

        if spy_df.empty:
            raise Exception("Failed to fetch SPY historical data")

        # Populate price history
        for price in spy_df['close'].tail(self.vol_lookback + 1):
            self.spy_prices.append(float(price))

        # Calculate current volatility
        self.current_volatility = self.calculate_volatility()

        # Get current regime
        current_regime = self.get_current_regime()
        if self.last_regime is None:
            self.last_regime = current_regime

        self.is_initialized = True
        self.logger.info(
            f"✓ Initialized! Volatility: {self.current_volatility:.1%}, "
            f"Regime: {current_regime}, "
            f"Frequency: {self.rebalance_frequency}"
        )

    def should_rebalance_today(self) -> bool:
        """
        Check if rebalancing needed based on configured frequency
        """
        if self.rebalance_frequency == 'daily':
            return self._check_daily_rebalance()
        elif self.rebalance_frequency == 'weekly':
            return self._check_weekly_rebalance()
        elif self.rebalance_frequency == 'monthly':
            return self._check_monthly_rebalance()
        elif self.rebalance_frequency == 'adaptive':
            return self._check_adaptive_rebalance()

        return False

    def _check_daily_rebalance(self) -> bool:
        """
        Daily: Rebalance when regime changes (max once per day)
        """
        today = datetime.now()

        # Don't rebalance twice same day
        if self.last_rebalance_date and self.last_rebalance_date.date() == today.date():
            self.logger.debug("Already rebalanced today")
            return False

        # Get current regime
        current_regime = self.get_current_regime()

        # Check if regime changed
        if self.last_regime and current_regime != self.last_regime:
            self.logger.info(f"Regime changed: {self.last_regime} → {current_regime}")
            return True

        # First run
        if self.last_regime is None:
            return True

        return False

    def _check_weekly_rebalance(self) -> bool:
        """
        Weekly: Rebalance every Friday
        """
        today = datetime.now()

        # Check if Friday
        if today.weekday() != 4:  # Friday = 4
            return False

        # Check if already rebalanced this week
        if self.last_rebalance_date:
            # Get ISO week number
            current_week = today.isocalendar()[1]
            current_year = today.year
            last_week = self.last_rebalance_date.isocalendar()[1]
            last_year = self.last_rebalance_date.year

            same_week = (current_week == last_week and current_year == last_year)

            if same_week:
                self.logger.info("Already rebalanced this week")
                return False

        self.logger.info("Weekly rebalance check: Friday")
        return True

    def _check_monthly_rebalance(self) -> bool:
        """
        Monthly: Rebalance at month-end (last 3 days of month)
        """
        today = datetime.now()

        # Check if month-end (last 3 days accounting for weekends)
        last_day = calendar.monthrange(today.year, today.month)[1]
        is_month_end = today.day >= last_day - 2

        if not is_month_end:
            return False

        # Check if already rebalanced this month
        if self.last_rebalance_date:
            same_month = (
                    self.last_rebalance_date.year == today.year and
                    self.last_rebalance_date.month == today.month
            )
            if same_month:
                self.logger.info(f"Already rebalanced this month on {self.last_rebalance_date.date()}")
                return False

        self.logger.info("Monthly rebalance check: Month-end")
        return True

    def _check_adaptive_rebalance(self) -> bool:
        """
        Adaptive: Rebalance on regime change OR weekly safety check
        Combines daily regime checking with weekly safety net
        """
        today = datetime.now()

        # First check: Has regime changed since last rebalance?
        current_regime = self.get_current_regime()
        regime_changed = (
                self.last_regime and
                current_regime != self.last_regime
        )

        if regime_changed:
            # Don't rebalance twice same day
            if self.last_rebalance_date and self.last_rebalance_date.date() == today.date():
                return False

            self.logger.info(f"Adaptive trigger: Regime changed {self.last_regime} → {current_regime}")
            return True

        # Second check: Weekly safety check (every Friday)
        if today.weekday() == 4:  # Friday
            if self.last_rebalance_date:
                days_since = (today - self.last_rebalance_date).days
                if days_since >= 7:
                    self.logger.info(f"Adaptive trigger: Weekly safety check ({days_since} days since last rebalance)")
                    return True
            else:
                # First run
                return True

        return False

    def calculate_volatility(self) -> float:
        """Calculate 20-day realized volatility (annualized)"""
        if len(self.spy_prices) < self.vol_lookback + 1:
            return None

        prices = list(self.spy_prices)
        returns = []

        for i in range(1, len(prices)):
            if prices[i] != 0:
                daily_return = (prices[i - 1] - prices[i]) / prices[i]
                returns.append(daily_return)

        if len(returns) < self.vol_lookback:
            return None

        return np.std(returns) * np.sqrt(252)

    def update_market_data(self):
        """Update latest prices and volatility before calculating signals"""
        # Get latest SPY price
        spy_df = self.data_provider.get_historical_bars('SPY', 2)
        if not spy_df.empty:
            latest_price = float(spy_df['close'].iloc[-1])
            self.spy_prices.append(latest_price)

        # Recalculate volatility
        self.current_volatility = self.calculate_volatility()

    def get_current_regime(self) -> str:
        """
        Determine current regime WITHOUT executing trades
        Used for regime-change detection
        """
        # Make sure we have latest data
        if self.current_volatility is None:
            self.update_market_data()

        if self.current_volatility is None:
            return "UNKNOWN"

        # Check recovery mode first
        if self.in_recovery_mode:
            if self.current_volatility < self.vol_low_threshold * 1.5:
                return "RECOVERY_LEVERAGE"
            else:
                return "RECOVERY_NEUTRAL"

        # Normal regime detection
        if self.current_volatility < self.vol_low_threshold:
            return "LOW_VOL_LEVERAGE"
        elif self.current_volatility > self.vol_high_threshold:
            return "HIGH_VOL_DEFENSIVE"
        else:
            return "MEDIUM_VOL_NEUTRAL"

    def check_recovery_mode(self):
        """Manage recovery mode status"""
        # Check for extreme volatility spike (proxy for VIX panic)
        if self.current_volatility and self.current_volatility > 0.50:  # 50% = extreme
            if not self.in_recovery_mode:
                self.in_recovery_mode = True
                self.recovery_mode_start = datetime.now()
                self.logger.info(f"🚨 RECOVERY MODE ACTIVATED - Vol: {self.current_volatility:.1%}")

        # Check if should exit recovery mode
        if self.in_recovery_mode and self.recovery_mode_start:
            days_in_recovery = (datetime.now() - self.recovery_mode_start).days

            # Exit if vol normalizes or timeout
            if (self.current_volatility and self.current_volatility < 0.20) or \
                    (days_in_recovery > self.max_recovery_days):
                self.in_recovery_mode = False
                self.logger.info(
                    f"✓ Recovery mode ended - Vol: {self.current_volatility:.1%}, Days: {days_in_recovery}")

    def calculate_signals(self) -> dict:
        """
        Calculate target allocation based on volatility regime
        Returns: dict {symbol: weight}
        """
        # Update latest market data
        self.update_market_data()

        if self.current_volatility is None:
            self.logger.warning("Volatility not available, holding SPY")
            allocation = {'SPY': 1.0}
            regime = "NO_DATA_NEUTRAL"

        else:
            # Check recovery mode
            self.check_recovery_mode()

            # Determine allocation
            if self.in_recovery_mode:
                if self.current_volatility < self.vol_low_threshold * 1.5:
                    allocation = {'UPRO': 1.0}
                    regime = "RECOVERY_LEVERAGE"
                else:
                    allocation = {'SPY': 1.0}
                    regime = "RECOVERY_NEUTRAL"

            elif self.current_volatility < self.vol_low_threshold:
                allocation = {'UPRO': 1.0}
                regime = "LOW_VOL_LEVERAGE"

            elif self.current_volatility > self.vol_high_threshold:
                allocation = {'SH': 1.0}
                regime = "HIGH_VOL_DEFENSIVE"

            else:
                allocation = {'SPY': 1.0}
                regime = "MEDIUM_VOL_NEUTRAL"

        # Log decision
        allocation_str = ", ".join([f"{sym}: {w:.0%}" for sym, w in allocation.items()])
        self.logger.info(
            f"📊 {regime} | {allocation_str} | Vol: {self.current_volatility:.1%} | "
            f"Frequency: {self.rebalance_frequency}"
        )

        # Update state BEFORE executing trades (crash-safe)
        self.trade_count += 1
        self.last_rebalance_date = datetime.now()
        self.last_regime = regime

        self.save_state({
            'last_rebalance_date': self.last_rebalance_date.isoformat(),
            'last_regime': self.last_regime,
            'trade_count': self.trade_count,
            'in_recovery_mode': self.in_recovery_mode,
            'recovery_mode_start': self.recovery_mode_start.isoformat() if self.recovery_mode_start else None,
        })

        return allocation