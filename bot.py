import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy

from config import get_settings
from database.seed import seed_districts_if_empty, seed_schools_from_csv_if_empty
from database.session import async_session_maker, init_db
from handlers import setup_routers
from middlewares.db import DbSessionMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    if not (settings.bot_token or "").strip():
        logger.error("BOT_TOKEN .env faylida ko'rsatilmagan — bot ishga tushmaydi.")
        sys.exit(1)
    if not (settings.required_channel_id or "").strip():
        logger.error("REQUIRED_CHANNEL_ID .env da ko'rsatilmagan — bot ishga tushmaydi.")
        sys.exit(1)
    logging.getLogger().setLevel(settings.log_level.upper())

    await init_db()
    async with async_session_maker() as session:
        d = await seed_districts_if_empty(session)
        n = await seed_schools_from_csv_if_empty(session)
        await session.commit()
        if d:
            logger.info("Seed: %s ta tuman yuklandi.", d)
        if n:
            logger.info("Seed: %s ta maktab yuklandi.", n)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # GLOBAL_USER: tuman filtri shaxsiy chatda saqlanadi, @bot qidiruv esa boshqa chatda —
    # USER_IN_CHAT bo'lsa FSM kaliti mos kelmaydi va maktablar chiqmay qolardi.
    dp = Dispatcher(storage=MemoryStorage(), fsm_strategy=FSMStrategy.GLOBAL_USER)
    dp.update.middleware(DbSessionMiddleware())

    dp.include_router(setup_routers())

    async def _preload_channel_invite(bot: Bot) -> None:
        from utils.channel_invite import preload_required_channel_join_url

        await preload_required_channel_join_url(bot)

    dp.startup.register(_preload_channel_invite)

    async def _setup_results_menu_button(bot: Bot) -> None:
        """Chap tarafdagi menyu tugmasini ommaviy natijalar mini-app sifatida o'rnatish (hamma uchun)."""
        from aiogram.types import MenuButtonCommands, MenuButtonWebApp, WebAppInfo

        base = (settings.web_admin_public_url or "").strip().rstrip("/")
        if not base.startswith("https://"):
            logger.warning(
                "WEB_ADMIN_PUBLIC_URL HTTPS emas — natijalar menyu tugmasi o'rnatilmadi (%r).",
                base or "(bo'sh)",
            )
            return
        results_url = f"{base}/results"
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="🏆 Natijalar", web_app=WebAppInfo(url=results_url)),
            )
            logger.info("Menyu tugmasi o'rnatildi: %s", results_url)
        except Exception as e:  # noqa: BLE001 — startupni to'xtatmaymiz
            logger.warning("Menyu tugmasini o'rnatib bo'lmadi: %s", e)
            try:
                await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            except Exception:
                pass

    dp.startup.register(_setup_results_menu_button)

    logger.info("Bot ishga tushmoqda…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
