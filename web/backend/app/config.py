from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Strader"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://strader:strader@db:5432/strader"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Schwab API
    schwab_app_key: str = ""
    schwab_app_secret: str = ""
    schwab_token_path: str = "/app/data/schwab_token.json"
    schwab_callback_url: str = "https://127.0.0.1:8443/callback"

    # Risk limits
    max_daily_loss: float = 5000.0
    max_position_count: int = 10
    max_single_position_notional: float = 5000.0
    max_portfolio_delta: float = 50.0
    risk_per_trade_pct: float = 2.0

    model_config = {"env_prefix": "STRADER_"}


settings = Settings()
