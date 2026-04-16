import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy

from config import get_settings
from database.seed import seed_directors_from_csv_if_empty, seed_districts_if_empty
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
        n = await seed_directors_from_csv_if_empty(session)
        await session.commit()
        if d:
            logger.info("Seed: %s ta tuman yuklandi.", d)
        if n:
            logger.info("Seed: %s ta direktor yuklandi.", n)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # GLOBAL_USER: tuman filtri shaxsiy chatda saqlanadi, @bot qidiruv esa boshqa chatda —
    # USER_IN_CHAT bo'lsa FSM kaliti mos kelmaydi va direktorlar chiqmay qolardi.
    dp = Dispatcher(storage=MemoryStorage(), fsm_strategy=FSMStrategy.GLOBAL_USER)
    dp.update.middleware(DbSessionMiddleware())

    dp.include_router(setup_routers())

    async def _preload_channel_invite(bot: Bot) -> None:
        from utils.channel_invite import preload_required_channel_join_url

        await preload_required_channel_join_url(bot)

    dp.startup.register(_preload_channel_invite)

    logger.info("Bot ishga tushmoqda…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
