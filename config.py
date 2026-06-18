from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(default="", validation_alias="BOT_TOKEN")
    # 1-majburiy Telegram kanal
    required_channel_id: str = Field(default="", validation_alias="REQUIRED_CHANNEL_ID")
    # 2-majburiy Telegram kanal (ixtiyoriy):
    # REQUIRED_CHANNEL_ID_2 — bot kanal admini qilinganidan keyin get_chat_member ishlashi uchun
    #   raqamli chat_id (masalan, -1001234567890) yoki @public_username.
    # REQUIRED_CHANNEL_2_JOIN_URL — foydalanuvchiga ko'rsatiladigan taklif havolasi (masalan, https://t.me/+...).
    required_channel_id_2: str = Field(default="", validation_alias="REQUIRED_CHANNEL_ID_2")
    required_channel_2_join_url: str = Field(default="", validation_alias="REQUIRED_CHANNEL_2_JOIN_URL")
    # Orqaga moslik: eski REQUIRED_GROUP_* sozlamalari endi 2-kanal sifatida ishlatiladi.
    required_group_id: str = Field(default="", validation_alias="REQUIRED_GROUP_ID")
    required_group_join_url: str = Field(default="", validation_alias="REQUIRED_GROUP_JOIN_URL")
    instagram_profile_url: str = Field(default="https://www.instagram.com/", validation_alias="INSTAGRAM_PROFILE_URL")
    # .env da vergul bilan: 111,222 — list[int] to'g'ridan-to'g'ri yozilsa pydantic-settings JSON kutadi va xato beradi.
    admin_ids_env: str = Field(default="", validation_alias="ADMIN_IDS")
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

    @computed_field
    @property
    def admin_ids(self) -> list[int]:
        raw = self.admin_ids_env.strip()
        if not raw:
            return []
        return [int(x.strip()) for x in raw.split(",") if x.strip()]

    @property
    def channel_2_id(self) -> str:
        """2-majburiy kanal chat_id/@username (yoki orqaga moslik uchun eski REQUIRED_GROUP_ID).

        Bo'sh bo'lsa — 2-kanal majburiy emas (faqat 1-kanal tekshiriladi).
        """
        return (self.required_channel_id_2 or self.required_group_id or "").strip()

    @property
    def channel_2_join_url(self) -> str:
        """2-kanal uchun .env dagi tayyor taklif havolasi (yoki eski REQUIRED_GROUP_JOIN_URL)."""
        return (self.required_channel_2_join_url or self.required_group_join_url or "").strip()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
