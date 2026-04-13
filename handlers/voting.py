import logging
import re

from aiogram import Bot, F, Router
from sqlalchemy.exc import IntegrityError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from database import repositories as repo
from utils.states import Voting

logger = logging.getLogger(__name__)
router = Router(name="voting")

DIST_PREFIX = re.compile(r"^dist:(?P<id>.+)$")


@router.callback_query(Voting.active, F.data.startswith("dist:"))
async def set_district_filter(
    query: CallbackQuery,
    session,
    state: FSMContext,
) -> None:
    m = DIST_PREFIX.match(query.data or "")
    raw = (m.group("id") if m else "").strip()
    await query.answer()
    msg = query.message
    if raw == "ALL":
        await state.update_data(district_id=None)
        if msg:
            await msg.answer("Filtr: barcha tumanlar.")
        return
    try:
        did = int(raw)
    except ValueError:
        if msg:
            await msg.answer("Noto'g'ri tuman tanlovi.")
        return
    d = await repo.get_district(session, did)
    if not d:
        if msg:
            await msg.answer("Tuman topilmadi.")
        return
    await state.update_data(district_id=did)
    if msg:
        await msg.answer(f"Filtr: {d.name}. Qidiruv faqat shu tumandagi maktab direktorlari bo'yicha.")


@router.inline_query()
async def inline_search_directors(
    inline_query: InlineQuery,
    session,
    state: FSMContext,
) -> None:
    """Ism-familiya bo'yicha qidiruv; FSM da tuman filtri."""
    st = await state.get_state()
    if st != Voting.active.state:
        await inline_query.answer(
            [],
            cache_time=0,
            is_personal=True,
            switch_pm_text="Ovoz berish uchun /start",
            switch_pm_parameter="vote",
        )
        return

    uid = inline_query.from_user.id
    if await repo.has_voted_by_telegram(session, uid):
        await inline_query.answer(
            [],
            cache_time=0,
            is_personal=True,
            switch_pm_text="Siz allaqachon ovoz bergansiz",
            switch_pm_parameter="done",
        )
        return

    data = await state.get_data()
    district_id: int | None = data.get("district_id")
    q = inline_query.query or ""
    directors = await repo.search_directors(session, q, district_id, limit=50)

    results: list[InlineQueryResultArticle] = []
    for d in directors:
        rid = f"d{d.id}"
        dist_name = d.district.name if d.district else ""
        subtitle = f"{dist_name} · {d.school_name}" if dist_name else d.school_name
        results.append(
            InlineQueryResultArticle(
                id=rid,
                title=d.full_name[:64],
                description=subtitle[:128] if subtitle else None,
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"Tanlangan direktor: <b>{d.full_name}</b>\n"
                        f"{d.school_name}\n{dist_name}\n\n"
                        "Ovoz yuborilmoqda…"
                    )
                ),
            )
        )

    await inline_query.answer(results, cache_time=10, is_personal=True)


@router.chosen_inline_result()
async def on_director_chosen(
    result: ChosenInlineResult,
    session,
    state: FSMContext,
    bot: Bot,
) -> None:
    uid = result.from_user.id
    raw_id = result.result_id or ""
    if not raw_id.startswith("d") or len(raw_id) < 2:
        return

    try:
        director_id = int(raw_id[1:])
    except ValueError:
        return

    if await repo.has_voted_by_telegram(session, uid):
        return

    user = await repo.get_user(session, uid)
    if not user or not user.phone_normalized:
        return

    if await repo.has_voted_by_phone(session, user.phone_normalized):
        return

    director = await repo.get_director(session, director_id)
    if not director:
        return

    try:
        await repo.create_vote(session, uid, director.id, user.phone_normalized)
    except IntegrityError as e:
        logger.warning("Ovoz dublikat (DB): %s", e)
        return

    await state.clear()
    dist_name = director.district.name if director.district else ""
    try:
        await bot.send_message(
            uid,
            f"✅ Ovozingiz qabul qilindi: <b>{director.full_name}</b>\n"
            f"{director.school_name}\n{dist_name}\n\nRahmat!",
        )
    except Exception as e:
        logger.warning("Foydalanuvchiga xabar yuborib bo'lmadi: %s", e)
