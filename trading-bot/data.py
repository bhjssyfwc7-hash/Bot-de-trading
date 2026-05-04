import ccxt
import pandas as pd
from config import config
from logger import logger


def get_exchange() -> ccxt.binance:
    params = {
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    }
    if not config.IS_PAPER:
        params["apiKey"] = config.API_KEY
        params["secret"] = config.API_SECRET

    exchange = ccxt.binance(params)

    if config.IS_PAPER:
        exchange.set_sandbox_mode(False)  # Public endpoints only in paper mode

    return exchange


def fetch_ohlcv(exchange: ccxt.Exchange, symbol: str = None, timeframe: str = None, limit: int = None) -> pd.DataFrame:
    symbol = symbol or config.SYMBOL
    timeframe = timeframe or config.TIMEFRAME
    limit = limit or config.LIMIT

    try:
        raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except ccxt.NetworkError as e:
        logger.error("Network error fetching OHLCV: %s", e)
        raise
    except ccxt.ExchangeError as e:
        logger.error("Exchange error fetching OHLCV: %s", e)
        raise

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)
    return df


def fetch_ticker(exchange: ccxt.Exchange, symbol: str = None) -> dict:
    symbol = symbol or config.SYMBOL
    return exchange.fetch_ticker(symbol)
