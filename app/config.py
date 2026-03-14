from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    auth_token: str = "change-me"
    webhook_secret: str = ""
    database_url: str = "sqlite:///ledger.db"
    app_pin: str = ""  # PIN for web access (leave empty to disable)
    session_secret: str = "noti-ledger-session-secret"  # secret for signing cookies

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
