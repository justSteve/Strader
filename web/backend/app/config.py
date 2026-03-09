from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://strader:strader_dev@localhost:5432/strader"
    redis_url: str = "redis://localhost:6379/0"

    schwab_api_key: str = ""
    schwab_app_secret: str = ""
    schwab_callback_url: str = "https://127.0.0.1:8443/callback"
    schwab_token_path: str = "./schwab_token.json"

    # Risk limits
    max_daily_loss: float = 2000.0
    max_position_count: int = 10
    max_single_position_size: float = 5000.0
    max_portfolio_delta: float = 50.0
    max_risk_per_trade_pct: float = 2.0

    class Config:
        env_file = ".env"


settings = Settings()
