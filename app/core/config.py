from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://news:news@127.0.0.1:5433/news_aggregator"
    app_timezone: str = "UTC"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    youtube_api_key: str | None = None
    digest_recipient_email: str | None = None
    resend_api_key: str | None = None
    email_from: str = "AI News Digest <onboarding@resend.dev>"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
