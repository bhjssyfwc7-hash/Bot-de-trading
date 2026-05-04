import requests
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import config
from logger import logger

_BASE = "https://api.kraken.com/0/public"

_PAIR_MAP = {
    "BTC/USDT": "XBTUSDT",
    "BTC/USD":  "XBTUSD",
    "ETH/USDT": "ETHUSD",
    "ETH/USD":  "ETHUSD",
    "SOL/USDT": "SOLUSDT",
    "SOL/USD":  "SOLUSD",
}

_TF_MAP = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440,
}


def _kraken_pair(symbol: str) -> str:
    return _PAIR_MAP.get(symbol.upper(), symbol.replace("/", "").upper())


def get_exchange():
    """Retained for backward compatibility. Kraken HTTP is used directly."""
    return None


def fetch_ohlcv(exchange=None, symbol: str = None, timeframe: str = None, limit: int = None) -> pd.DataFrame:
    symbol    = symbol    or config.SYMBOL
    timeframe = timeframe or config.TIMEFRAME
    limit     = limit     or config.LIMIT
    interval  = _TF_MAP.get(timeframe, 60)

    try:
        r = requests.get(
            f"{_BASE}/OHLC",
            params={"pair": _kraken_pair(symbol), "interval": interval},
            verify=False,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data["error"]:
            raise ValueError(f"Kraken API error: {data['error']}")
        rows = [v for k, v in data["result"].items() if k != "last"][0]
        rows = rows[-limit:]
    except requests.RequestException as exc:
        logger.error("Network error fetching OHLCV: %s", exc)
        raise

    df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "vwap", "volume", "count"],
    )
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)
    return df


def fetch_ticker(exchange=None, symbol: str = None) -> dict:
    symbol = symbol or config.SYMBOL
    try:
        r = requests.get(
            f"{_BASE}/Ticker",
            params={"pair": _kraken_pair(symbol)},
            verify=False,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data["error"]:
            raise ValueError(f"Kraken API error: {data['error']}")
        result = list(data["result"].values())[0]
    except requests.RequestException as exc:
        logger.error("Network error fetching ticker: %s", exc)
        raise

    return {
        "last":   float(result["c"][0]),
        "ask":    float(result["a"][0]),
        "bid":    float(result["b"][0]),
        "volume": float(result["v"][1]),
    }
