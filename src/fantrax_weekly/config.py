from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    fantrax_user_secret_id: str
    fantrax_league_id: str
    anthropic_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
