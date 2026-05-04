import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Binance API credentials
    API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

    # Trading mode
    TRADING_MODE: str = os.getenv("TRADING_MODE", "paper").lower()
    IS_PAPER: bool = TRADING_MODE == "paper"

    # Market settings
    SYMBOL: str = os.getenv("SYMBOL", "BTC/USDT")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "1h")
    LIMIT: int = 200  # Number of candles to fetch

    # RSI strategy parameters
    RSI_PERIOD: int = int(os.getenv("RSI_PERIOD", 14))
    RSI_OVERSOLD: float = float(os.getenv("RSI_OVERSOLD", 30))
    RSI_OVERBOUGHT: float = float(os.getenv("RSI_OVERBOUGHT", 70))

    # Risk management
    RISK_PER_TRADE: float = float(os.getenv("RISK_PER_TRADE", 0.02))
    STOP_LOSS_PCT: float = float(os.getenv("STOP_LOSS_PCT", 0.02))
    TAKE_PROFIT_PCT: float = float(os.getenv("TAKE_PROFIT_PCT", 0.04))
    INITIAL_BALANCE: float = float(os.getenv("INITIAL_BALANCE", 1000.0))

    # Loop interval in seconds (matches timeframe approximately)
    LOOP_INTERVAL: int = 60  # Check every 60 seconds in live mode

    @classmethod
    def validate(cls) -> None:
        if not cls.IS_PAPER and (not cls.API_KEY or not cls.API_SECRET):
            raise ValueError(
                "BINANCE_API_KEY and BINANCE_API_SECRET must be set for live trading."
            )
        if cls.TRADING_MODE not in ("paper", "live"):
            raise ValueError("TRADING_MODE must be 'paper' or 'live'.")
        if not (0 < cls.RISK_PER_TRADE <= 0.1):
            raise ValueError("RISK_PER_TRADE must be between 0 and 0.10 (10%).")


config = Config()
