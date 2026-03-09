from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Strader"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://strader:strader_dev@localhost:5432/strader"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Schwab API
    schwab_app_key: str = ""
    schwab_app_secret: str = ""
    schwab_token_path: str = "./tokens/token.json"
    schwab_callback_url: str = "https://127.0.0.1:8182"

    # Risk limits
    max_daily_loss: float = -2000.0
    max_position_count: int = 10
    max_single_position: float = 5000.0
    max_portfolio_delta: float = 50.0

    # WebSocket
    ws_heartbeat_interval: int = 15

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
