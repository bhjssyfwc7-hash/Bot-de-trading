import pandas as pd
from config import config
from logger import log_signal


SIGNAL_BUY = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_HOLD = "HOLD"


def compute_rsi(df: pd.DataFrame) -> pd.Series:
    """Wilder's RSI using exponential smoothing (identical to the standard definition)."""
    period = config.RSI_PERIOD
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # First average uses simple mean over the initial window
    avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    return rsi


def get_signal(df: pd.DataFrame) -> str:
    df = df.copy()
    df["rsi"] = compute_rsi(df)

    last_rsi = df["rsi"].iloc[-1]
    prev_rsi = df["rsi"].iloc[-2]

    # Buy: RSI crosses INTO oversold zone (drops below 30)
    if prev_rsi >= config.RSI_OVERSOLD and last_rsi < config.RSI_OVERSOLD:
        signal = SIGNAL_BUY
    # Sell: RSI crosses INTO overbought zone (rises above 70)
    elif prev_rsi <= config.RSI_OVERBOUGHT and last_rsi > config.RSI_OVERBOUGHT:
        signal = SIGNAL_SELL
    else:
        signal = SIGNAL_HOLD

    log_signal(config.SYMBOL, last_rsi, signal)
    return signal


def get_latest_rsi(df: pd.DataFrame) -> float:
    return compute_rsi(df).iloc[-1]
