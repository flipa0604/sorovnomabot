from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(default="", validation_alias="BOT_TOKEN")
    required_channel_id: str = Field(default="", validation_alias="REQUIRED_CHANNEL_ID")
    instagram_profile_url: str = Field(default="https://www.instagram.com/", validation_alias="INSTAGRAM_PROFILE_URL")
    admin_ids: list[int] = Field(default_factory=list, validation_alias="ADMIN_IDS")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/bot.db",
        validation_alias="DATABASE_URL",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # Web-admin (FastAPI): tuman/maktab CRUD va ovozlar statistikasi
    web_admin_secret: str = Field(
        default="o'zgartiring-dev uchun",
        validation_alias="WEB_ADMIN_SECRET",
    )
    web_admin_username: str = Field(default="admin", validation_alias="WEB_ADMIN_USERNAME")
    web_admin_password: str = Field(default="", validation_alias="WEB_ADMIN_PASSWORD")
    web_admin_host: str = Field(default="127.0.0.1", validation_alias="WEB_ADMIN_HOST")
    web_admin_port: int = Field(default=8765, validation_alias="WEB_ADMIN_PORT")
    # HTTPS veb-admin domeni (Telegram Web App / brauzer): masalan https://admin.bimu.uz
    web_admin_public_url: str = Field(default="", validation_alias="WEB_ADMIN_PUBLIC_URL")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: str | list[int] | int) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, int):
            return [v]
        if isinstance(v, str) and v.strip():
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return []

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
