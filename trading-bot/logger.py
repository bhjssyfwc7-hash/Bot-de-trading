import logging
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_log_filename = os.path.join(LOG_DIR, f"trades_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(_log_filename),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("trading_bot")


def quiet_console() -> None:
    """Raise console handler threshold to WARNING so INFO logs don't clutter the dashboard."""
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.WARNING)


def log_trade(action: str, symbol: str, price: float, qty: float, balance: float) -> None:
    logger.info(
        "TRADE | %-4s | %s | price=%.4f | qty=%.6f | balance=%.2f USDT",
        action, symbol, price, qty, balance,
    )


def log_signal(symbol: str, rsi: float, signal: str) -> None:
    logger.info("SIGNAL | %s | RSI=%.2f | signal=%s", symbol, rsi, signal)
