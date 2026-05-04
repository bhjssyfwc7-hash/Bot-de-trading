from config import config
from logger import logger


def position_size(balance: float, entry_price: float) -> float:
    """Return the quantity to buy based on fixed-fractional risk."""
    risk_amount = balance * config.RISK_PER_TRADE
    stop_distance = entry_price * config.STOP_LOSS_PCT
    qty = risk_amount / stop_distance
    # Cap at the affordable amount given the full balance
    max_qty = (balance / entry_price) * 0.95  # keep 5% cash buffer
    qty = min(qty, max_qty)
    logger.debug(
        "Position size: balance=%.2f entry=%.4f risk_amount=%.2f qty=%.6f",
        balance,
        entry_price,
        risk_amount,
        qty,
    )
    return qty


def stop_loss_price(entry_price: float) -> float:
    return entry_price * (1 - config.STOP_LOSS_PCT)


def take_profit_price(entry_price: float) -> float:
    return entry_price * (1 + config.TAKE_PROFIT_PCT)


def check_exit(current_price: float, entry_price: float) -> str | None:
    """Return 'STOP_LOSS', 'TAKE_PROFIT', or None."""
    if current_price <= stop_loss_price(entry_price):
        return "STOP_LOSS"
    if current_price >= take_profit_price(entry_price):
        return "TAKE_PROFIT"
    return None
