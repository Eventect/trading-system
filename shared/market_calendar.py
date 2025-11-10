# shared/market_calendar.py
from datetime import datetime, time
import pytz
from typing import Optional


class MarketCalendar:
    """
    Handle US market hours and timezone conversions
    Market hours: 9:30 AM - 4:00 PM ET
    """

    def __init__(self):
        self.market_tz = pytz.timezone('America/New_York')
        self.utc_tz = pytz.UTC

        # Market hours in ET
        self.market_open = time(9, 30)
        self.market_close = time(16, 0)

        # Extended hours
        self.pre_market_open = time(4, 0)
        self.after_market_close = time(20, 0)

    def get_market_time(self) -> datetime:
        """Get current time in market timezone (ET)"""
        return datetime.now(self.market_tz)

    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open
        Does NOT check if today is a trading day (weekends/holidays)
        """
        if check_time is None:
            check_time = self.get_market_time()
        elif check_time.tzinfo is None:
            check_time = self.market_tz.localize(check_time)
        else:
            check_time = check_time.astimezone(self.market_tz)

        current_time = check_time.time()

        # Check if it's a weekday
        if check_time.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        return self.market_open <= current_time <= self.market_close

    def is_time_to_rebalance(self, target_time: time = time(15, 30)) -> bool:
        """
        Check if it's time to rebalance (default: 3:30 PM ET)
        Called every minute to check
        """
        now = self.get_market_time()

        # Check if weekday
        if now.weekday() >= 5:
            return False

        current_time = now.time()

        # Check if we're within 1 minute of target time
        target_hour = target_time.hour
        target_minute = target_time.minute

        is_target_time = (
                current_time.hour == target_hour and
                current_time.minute == target_minute
        )

        return is_target_time

    def get_next_market_day(self, from_date: Optional[datetime] = None) -> datetime:
        """Get next market day (skips weekends, NOT holidays)"""
        if from_date is None:
            from_date = self.get_market_time()

        next_day = from_date
        while True:
            next_day = next_day.replace(hour=9, minute=30, second=0, microsecond=0)
            next_day = next_day + timedelta(days=1)

            if next_day.weekday() < 5:  # Weekday
                return next_day

    def time_until_next_check(self) -> int:
        """
        Return seconds until next check time
        Always returns 60 (check every minute)
        """
        return 60