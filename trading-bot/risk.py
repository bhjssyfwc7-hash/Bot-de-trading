from config import config
from logger import logger


# ── Position sizing ───────────────────────────────────────────────────────────

def position_size(portfolio_value: float, entry_price: float) -> float:
    """
    Allocate CAPITAL_PER_TRADE (5%) of portfolio value to this position.
    Returns quantity in crypto units.
    """
    capital = portfolio_value * config.CAPITAL_PER_TRADE
    qty = capital / entry_price
    logger.debug(
        "Position size: portfolio=%.2f  capital=%.2f  entry=%.4f  qty=%.8f",
        portfolio_value, capital, entry_price, qty,
    )
    return qty


# ── Exit levels ───────────────────────────────────────────────────────────────

def stop_loss_price(entry_price: float) -> float:
    """Stop-loss at -0.5% from entry."""
    return entry_price * (1 - config.STOP_LOSS_PCT)


def take_profit_price(entry_price: float) -> float:
    """Take-profit at +1.0% from entry (2:1 ratio)."""
    return entry_price * (1 + config.TAKE_PROFIT_PCT)


def check_exit(current_price: float, entry_price: float) -> str | None:
    """Return 'STOP_LOSS', 'TAKE_PROFIT', or None."""
    if current_price <= stop_loss_price(entry_price):
        return "STOP_LOSS"
    if current_price >= take_profit_price(entry_price):
        return "TAKE_PROFIT"
    return None


# ── Daily loss guard ──────────────────────────────────────────────────────────

def is_daily_loss_exceeded(portfolio_value: float, day_start_value: float) -> bool:
    """Return True when the daily drawdown exceeds MAX_DAILY_LOSS_PCT."""
    if day_start_value <= 0:
        return False
    daily_return = (portfolio_value - day_start_value) / day_start_value
    return daily_return <= -config.MAX_DAILY_LOSS_PCT
