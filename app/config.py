from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    auth_token: str = "change-me"
    webhook_secret: str = ""
    database_url: str = "sqlite:///ledger.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
