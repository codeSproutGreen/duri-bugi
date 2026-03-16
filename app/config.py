from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""  # Deprecated: kept for backward compat
    gemini_api_key: str = ""
    auth_token: str = "change-me"
    webhook_secret: str = ""
    database_url: str = "sqlite:///ledger.db"
    app_pin: str = ""  # Deprecated: single PIN (kept for backward compat)
    app_pins: str = ""  # Multi-user PINs, format: "1234:아내,5678:남편"
    session_secret: str = "noti-ledger-session-secret"  # secret for signing cookies

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
