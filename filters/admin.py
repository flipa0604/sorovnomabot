from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import get_settings


class AdminFilter(Filter):
    """Faqat .env dagi ADMIN_IDS ro'yxatidagi foydalanuvchilar."""

    async def __call__(self, event: TelegramObject) -> bool:
        settings = get_settings()
        if not settings.admin_ids:
            return False
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        elif hasattr(event, "from_user"):
            user = event.from_user
        if not user:
            return False
        return user.id in settings.admin_ids
