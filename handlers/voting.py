import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)
from sqlalchemy.exc import IntegrityError

from database import repositories as repo
from utils.keyboards import (
    director_detail_keyboard,
    district_filter_keyboard,
    schools_page_keyboard,
    vote_start_deeplink_url,
)
from utils.states import Voting

logger = logging.getLogger(__name__)
router = Router(name="voting")

DIST_PREFIX = re.compile(r"^dist:(?P<id>.+)$")
DIRECTOR_INLINE_QUERY = re.compile(r"^d(\d+)\s*$", re.IGNORECASE)

PER_PAGE = 20


class DirectorShareInlineFilter(BaseFilter):
    """Inline so'rov: @bot d123 (direktor id)."""

    async def __call__(self, inline_query: InlineQuery) -> bool:
        return bool(DIRECTOR_INLINE_QUERY.match((inline_query.query or "").strip()))


def _detail_html(director) -> str:
    dist_name = director.district.name if director.district else ""
    parts = [
        f"🏫 <b>{html.escape(director.school_name or '')}</b>",
        f"👤 <b>{html.escape(director.full_name or '')}</b>",
    ]
    if dist_name:
        parts.append(f"📍 {html.escape(dist_name)}")
    return "\n".join(parts)


def _school_list_caption(district_name: str, page: int, total_pages: int) -> str:
    return (
        f"📍 <b>{html.escape(district_name)}</b>\n"
        f"📄 <b>{page + 1}/{total_pages}</b> sahifa\n"
        f"🏫 <i>Maktabni tanlang:</i>"
    )


async def _validate_voter(session, uid: int) -> tuple[bool, str | None]:
    user = await repo.get_user(session, uid)
    if not user or not user.phone_normalized:
        return False, "⚠️ Avval /start bilan ro'yxatdan o'ting."
    return True, None


async def _apply_vote_after_confirmed(session, uid: int, director_id: int) -> tuple[bool, str | None]:
    director = await repo.get_director(session, director_id)
    if not director:
        return False, "❌ Maktab topilmadi."
    try:
        await repo.upsert_user_vote(session, uid, director.id)
    except IntegrityError as e:
        logger.warning("Ovoz saqlash xatosi: %s", e)
        return False, "❌ Saqlab bo'lmadi."
    return True, None


async def _send_vote_success(bot: Bot, uid: int, director, *, changed: bool) -> None:
    dist_name = director.district.name if director.district else ""
    head = "🔄 Ovoz yangilandi!" if changed else "✅ Ovoz qabul qilindi!"
    try:
        await bot.send_message(
            uid,
            f"{head}\n\n"
            f"👤 <b>{html.escape(director.full_name or '')}</b>\n"
            f"🏫 {html.escape(director.school_name or '')}\n"
            f"📍 {html.escape(dist_name)}\n\n"
            "🙏 Rahmat!",
        )
    except Exception as e:
        logger.warning("Foydalanuvchiga xabar yuborib bo'lmadi: %s", e)


@router.callback_query(F.data.startswith("vch:"))
async def callback_vote_change_confirmed(
    query: CallbackQuery,
    session,
    state: FSMContext,
    bot: Bot,
) -> None:
    raw = (query.data or "").split(":", 1)
    if len(raw) < 2:
        await query.answer()
        return
    try:
        director_id = int(raw[1])
    except ValueError:
        await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return

    uid = query.from_user.id
    okv, err = await _validate_voter(session, uid)
    if not okv:
        await query.answer(err or "Xato", show_alert=True)
        return

    ok, err = await _apply_vote_after_confirmed(session, uid, director_id)
    if not ok:
        await query.answer(err or "Xato", show_alert=True)
        return

    await query.answer("✅")
    director = await repo.get_director(session, director_id)
    if director:
        await _send_vote_success(bot, uid, director, changed=True)
    await state.clear()
    try:
        await query.message.edit_text(
            "✅ <b>Ovoz yangilandi.</b>\n🙏 Rahmat!",
            reply_markup=None,
        )
    except TelegramBadRequest:
        if query.message:
            await query.message.answer("✅ Ovoz yangilandi. Rahmat!", )


@router.callback_query(F.data == "vca")
async def callback_vote_change_cancel(query: CallbackQuery) -> None:
    await query.answer("Bekor qilindi")
    try:
        await query.message.edit_text(
            "❎ <b>O'zgartirilmadi.</b>",
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("vok:"))
async def callback_confirm_vote(
    query: CallbackQuery,
    session,
    state: FSMContext,
    bot: Bot,
) -> None:
    raw = (query.data or "").split(":", 1)
    if len(raw) < 2:
        await query.answer()
        return
    try:
        director_id = int(raw[1])
    except ValueError:
        await query.answer("❌ Noto'g'ri ma'lumot.", show_alert=True)
        return

    uid = query.from_user.id
    okv, err = await _validate_voter(session, uid)
    if not okv:
        await query.answer(err or "Xato", show_alert=True)
        return

    director = await repo.get_director(session, director_id)
    if not director:
        await query.answer("❌ Maktab topilmadi.", show_alert=True)
        return

    current = await repo.get_user_vote(session, uid)
    if current and current.director_id == director_id:
        await query.answer("ℹ️ Shu maktabga allaqachon ovoz bergansiz.", show_alert=True)
        return

    if current and current.director_id != director_id:
        old_d = current.director
        if not old_d:
            old_d = await repo.get_director(session, current.director_id)
        old_dist = (old_d.district.name if old_d and old_d.district else "") or "—"
        old_name = (old_d.full_name if old_d else "") or "—"
        old_school = (old_d.school_name if old_d else "") or "—"
        text = (
            "⚠️ <b>Ovozni o'zgartirish</b>\n\n"
            f"📍 {html.escape(old_dist)}\n"
            f"🏫 <i>{html.escape(old_school)}</i>\n"
            f"👤 {html.escape(old_name)}\n\n"
            "Yangi tanlovga o'tasizmi?"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Ha", callback_data=f"vch:{director_id}"),
                    InlineKeyboardButton(text="❌ Yo'q", callback_data="vca"),
                ],
            ]
        )
        await query.answer()
        try:
            await query.message.edit_text(text, reply_markup=kb, )
        except TelegramBadRequest:
            await query.message.answer(text, reply_markup=kb, )
        return

    ok, err = await _apply_vote_after_confirmed(session, uid, director_id)
    if not ok:
        await query.answer(err or "Xato", show_alert=True)
        return

    await query.answer("✅")
    if director:
        await _send_vote_success(bot, uid, director, changed=False)
    await state.clear()
    try:
        await query.message.edit_text(
            "✅ <b>Ovoz qabul qilindi.</b>\n🙏 Rahmat!",
            reply_markup=None,
        )
    except TelegramBadRequest:
        if query.message:
            await query.message.answer("✅ Ovoz qabul qilindi. Rahmat!",)


@router.callback_query(Voting.active, F.data.startswith("pg:"))
async def callback_schools_page(
    query: CallbackQuery,
    session,
) -> None:
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.answer()
        return
    try:
        district_id = int(parts[1])
        page = int(parts[2])
    except ValueError:
        await query.answer()
        return

    district = await repo.get_district(session, district_id)
    if not district:
        await query.answer("❌ Tuman topilmadi.", show_alert=True)
        return

    total = await repo.count_directors_in_district(session, district_id)
    if total == 0:
        await query.answer()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Tumanlar", callback_data="nav:distlist")]]
        )
        try:
            await query.message.edit_text(
                f"📍 <b>{html.escape(district.name)}</b>\n\n"
                "🏚 <i>Bu tumanda maktablar hali yo'q.</i>",
                reply_markup=kb,
            )
        except TelegramBadRequest:
            pass
        return

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    directors = await repo.list_directors_by_district_school_page(session, district_id, page, PER_PAGE)
    text = _school_list_caption(district.name, page, total_pages)
    kb = schools_page_keyboard(directors, district_id, page, total, PER_PAGE)
    await query.answer()
    try:
        await query.message.edit_text(text, reply_markup=kb, )
    except TelegramBadRequest as e:
        logger.warning("Xabarni tahrirlab bo'lmadi: %s", e)
        await query.message.answer(text, reply_markup=kb, )


@router.callback_query(Voting.active, F.data.startswith("dt:"))
async def callback_director_detail(
    query: CallbackQuery,
    session,
) -> None:
    parts = (query.data or "").split(":")
    if len(parts) != 4:
        await query.answer()
        return
    try:
        director_id = int(parts[1])
        district_id = int(parts[2])
        list_page = int(parts[3])
    except ValueError:
        await query.answer()
        return

    director = await repo.get_director(session, director_id)
    if not director:
        await query.answer("❌ Maktab topilmadi.", show_alert=True)
        return

    text = _detail_html(director) + "\n\n<i>Quyidagilardan birini tanlang:</i>"
    kb = director_detail_keyboard(director_id, district_id, list_page)
    await query.answer()
    try:
        await query.message.edit_text(text, reply_markup=kb, )
    except TelegramBadRequest as e:
        logger.warning("Xabarni tahrirlab bo'lmadi: %s", e)
        await query.message.answer(text, reply_markup=kb, )


@router.callback_query(Voting.active, F.data == "nav:distlist")
async def callback_back_to_districts(
    query: CallbackQuery,
    session,
    state: FSMContext,
) -> None:
    districts = await repo.list_districts(session)
    await query.answer()
    if not districts:
        await query.message.answer("⚠️ Tumanlar ro'yxati bo'sh.")
        return
    await state.update_data(district_id=None)
    text = "🗺 <b>Tuman tanlang</b>\n<i>Keyin maktab ro'yxati ochiladi.</i>"
    try:
        await query.message.edit_text(
            text,
            reply_markup=district_filter_keyboard(districts),
        )
    except TelegramBadRequest:
        await query.message.answer(
            text,
            reply_markup=district_filter_keyboard(districts),
        )


@router.callback_query(Voting.active, F.data.startswith("dist:"))
async def set_district_and_show_schools(
    query: CallbackQuery,
    session,
    state: FSMContext,
) -> None:
    m = DIST_PREFIX.match(query.data or "")
    raw = (m.group("id") if m else "").strip()
    await query.answer()
    msg = query.message
    if not msg:
        return

    try:
        did = int(raw)
    except ValueError:
        try:
            await msg.edit_text("❌ Noto'g'ri tanlov.", )
        except TelegramBadRequest:
            await msg.answer("❌ Noto'g'ri tanlov.")
        return

    d = await repo.get_district(session, did)
    if not d:
        try:
            await msg.edit_text("❌ Tuman topilmadi.", )
        except TelegramBadRequest:
            await msg.answer("❌ Tuman topilmadi.")
        return

    await state.update_data(district_id=did)

    total = await repo.count_directors_in_district(session, did)
    kb_back = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Tumanlar", callback_data="nav:distlist")]]
    )
    if total == 0:
        try:
            await msg.edit_text(
                f"📍 <b>{html.escape(d.name)}</b>\n\n"
                "🏚 <i>Maktablar hali kiritilmagan.</i>",
                reply_markup=kb_back,
            )
        except TelegramBadRequest:
            await msg.answer(
                f"📍 <b>{html.escape(d.name)}</b>\n\n🏚 Maktablar hali kiritilmagan.",
                reply_markup=kb_back,
            )
        return

    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    directors = await repo.list_directors_by_district_school_page(session, did, 0, PER_PAGE)
    text = _school_list_caption(d.name, 0, total_pages)
    kb = schools_page_keyboard(directors, did, 0, total, PER_PAGE)
    try:
        await msg.edit_text(text, reply_markup=kb, )
    except TelegramBadRequest as e:
        logger.warning("Tahrir xato: %s", e)
        await msg.answer(text, reply_markup=kb, )


@router.inline_query(DirectorShareInlineFilter())
async def inline_share_director(
    inline_query: InlineQuery,
    session,
    bot: Bot,
) -> None:
    """d{id} — boshqa chatda ulashish (tashqidagi ovoz uchun havola)."""
    m = DIRECTOR_INLINE_QUERY.match((inline_query.query or "").strip())
    if not m:
        await inline_query.answer([], cache_time=0, is_personal=True)
        return
    director_id = int(m.group(1))
    director = await repo.get_director(session, director_id)
    if not director:
        await inline_query.answer([], cache_time=0, is_personal=True)
        return

    me = await bot.get_me()
    uname = me.username or ""
    if not uname:
        await inline_query.answer([], cache_time=0, is_personal=True)
        return

    dist_name = director.district.name if director.district else ""
    title = (director.school_name or director.full_name or "Maktab")[:64]
    desc = (f"{director.full_name} · {dist_name}" if dist_name else (director.full_name or ""))[:128]

    body_lines = [
        f"🏫 <b>{html.escape(director.school_name or '')}</b>",
        f"👤 <b>{html.escape(director.full_name or '')}</b>",
    ]
    if dist_name:
        body_lines.append(f"📍 {html.escape(dist_name)}")
    body_lines.extend(["", "👇 <i>Botda ovoz berish:</i>"])
    message_text = "\n".join(body_lines)

    vote_url = vote_start_deeplink_url(uname, director_id)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🗳 Botda ovoz berish", url=vote_url)]]
    )

    results = [
        InlineQueryResultArticle(
            id=f"d{director_id}",
            title=title,
            description=desc or None,
            input_message_content=InputTextMessageContent(
                message_text=message_text,
                parse_mode="HTML",
            ),
            reply_markup=markup,
        )
    ]
    await inline_query.answer(results, cache_time=30, is_personal=False)


@router.inline_query()
async def inline_query_fallback(inline_query: InlineQuery) -> None:
    await inline_query.answer(
        [],
        cache_time=0,
        is_personal=True,
        switch_pm_text="🏠 Botda /start",
        switch_pm_parameter="vote",
    )


async def offer_vote_from_start_payload(
    message: Message,
    session,
    state: FSMContext,
    director_id: int,
) -> None:
    """/start d{id} — tasdiq."""
    director = await repo.get_director(session, director_id)
    if not director:
        await message.answer("❌ Maktab topilmadi.")
        return
    await state.set_state(Voting.active)
    text = _detail_html(director) + "\n\n👇 <b>Ovoz berish</b> tugmasini bosing."
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Ovoz berish", callback_data=f"vok:{director_id}")]]
    )
    await message.answer(text, reply_markup=kb, )
