import html
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Contact, Message, ReplyKeyboardRemove

from config import get_settings
from database import repositories as repo
from handlers.voting import offer_vote_from_start_payload
from utils.deeplink import parse_director_start_payload
from utils.keyboards import contact_keyboard, district_filter_keyboard, instagram_confirm_keyboard
from utils.phone import normalize_phone
from utils.states import Registration, Voting

logger = logging.getLogger(__name__)
router = Router(name="registration")


async def user_is_channel_member(bot: Bot, user_id: int) -> bool:
    settings = get_settings()
    try:
        m = await bot.get_chat_member(chat_id=settings.required_channel_id, user_id=user_id)
    except TelegramBadRequest as e:
        logger.warning("Kanal tekshiruvi xatolik: %s", e)
        return False
    return m.status in (
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    )


async def enter_voting_stage(
    message: Message,
    session,
    state: FSMContext,
    telegram_id: int,
    bot: Bot,
) -> None:
    await repo.set_user_flags(session, telegram_id, channel_ok=True, instagram_ok=True)
    await state.set_state(Voting.active)
    await state.update_data(district_id=None)
    districts = await repo.list_districts(session)
    me = await bot.get_me()
    uname = me.username or "bot"
    if not districts:
        await message.answer(
            "⚠️ <b>Tumanlar yo'q.</b>\nAdmin web-panel orqali qo'shing.",
        )
        return
    await message.answer(
        "🗳 <b>Ovoz berish</b>\n\n"
        "1) Pastdagi tugmalar orqali <b>tumanni</b> tanlang.\n\n"
        "2) Ro'yxatdan maktabni tanlang va shu maktab direktoriga ovoz bering.\n\n"
        "ℹ️ Faqat bitta ovoz bera olasiz!",
        reply_markup=district_filter_keyboard(districts),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📋 <b>So'rovnoma boti</b>\n\n"
        "📢 Kanal → 📷 Instagram → 📱 Telefon → 🗳 Ovoz\n\n"
        "/start — boshlash",
        parse_mode=ParseMode.HTML,
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session,
    state: FSMContext,
    bot: Bot,
) -> None:
    uid = message.from_user.id
    await repo.get_or_create_user(
        session,
        uid,
        message.from_user.username,
        message.from_user.full_name,
    )

    director_id = parse_director_start_payload(command.args)

    if await user_is_channel_member(bot, uid):
        await repo.set_user_flags(session, uid, channel_ok=True)
        u = await repo.get_user(session, uid)
        if director_id is not None and u and u.instagram_ok and u.phone_normalized:
            await offer_vote_from_start_payload(message, session, state, director_id)
            return
        if u and u.instagram_ok and u.phone_normalized:
            await enter_voting_stage(message, session, state, uid, bot)
            return
        if not u or not u.instagram_ok:
            await state.set_state(Registration.wait_instagram)
            await message.answer(
                "📷 <b>Instagram</b>\nHavolani oching va instagram profilimizga obuna bo'ling, keyin <b>✅ Tasdiqlash</b> tugmasini bosing.",
                reply_markup=instagram_confirm_keyboard(get_settings().instagram_profile_url),
            )
            return
        await state.set_state(Registration.wait_phone)
        await message.answer(
            "📱 <b>Telefon</b>\nPastdagi tugma orqali ulashing.",
            reply_markup=contact_keyboard(),
        )
        return

    await state.set_state(Registration.wait_subscription)
    ch = get_settings().required_channel_id
    pretty = ch if ch.startswith("@") else f"kanal ({ch})"

    from utils.channel_invite import get_required_channel_join_url
    from utils.keyboards import channel_keyboard

    try:
        join_url = await get_required_channel_join_url(bot)
    except Exception as e:
        logger.warning("Kanal taklif havolasi: %s", e)
        join_url = f"https://t.me/{ch.lstrip('@')}" if ch.startswith("@") else "https://t.me/telegram"

    await message.answer(
        f"📢 <b>Kanal</b>\n{html.escape(pretty)} ga qo'shiling, keyin <b>✅ A'zolikni tekshirish</b>.",
        reply_markup=channel_keyboard(join_url),
        parse_mode=ParseMode.HTML,
    )

@router.callback_query(F.data == "sub:check")
async def callback_check_subscription(
    query: CallbackQuery,
    session,
    state: FSMContext,
    bot: Bot,
) -> None:
    await query.answer()
    uid = query.from_user.id
    if not await user_is_channel_member(bot, uid):
        await query.message.answer(
            "⚠️ Kanalda a'zo emassiz.\nAvval qo'shiling, keyin qayta tekshiring.",
        )
        return

    await repo.set_user_flags(session, uid, channel_ok=True)
    await state.set_state(Registration.wait_instagram)
    await query.message.answer(
        "✅ <b>Kanal OK</b>\n\n📷 Instagram — havola, keyin <b>✅ Ko'rdim</b>.",
        reply_markup=instagram_confirm_keyboard(get_settings().instagram_profile_url),
    )


@router.callback_query(F.data == "ig:confirm")
async def callback_instagram(
    query: CallbackQuery,
    session,
    state: FSMContext,
) -> None:
    await query.answer()
    uid = query.from_user.id
    await repo.set_user_flags(session, uid, instagram_ok=True)
    await state.set_state(Registration.wait_phone)
    await query.message.answer(
        "📱 <b>Telefon</b>\nTugma orqali ulashing.",
        reply_markup=contact_keyboard(),
    )


@router.message(Registration.wait_phone, F.contact)
async def on_contact(
    message: Message,
    session,
    state: FSMContext,
) -> None:
    contact: Contact = message.contact
    if contact.user_id is not None and contact.user_id != message.from_user.id:
        await message.answer("⚠️ Faqat <b>o'z</b> kontaktingiz.", parse_mode=ParseMode.HTML)
        return

    phone = normalize_phone(contact.phone_number or "")
    if len(phone) < 12:
        await message.answer("❌ Raqam noto'g'ri. Qayta yuboring.")
        return

    uid = message.from_user.id
    if await repo.phone_taken_by_other(session, phone, uid):
        await message.answer(
            "❌ Bu raqam boshqa akkauntga bog'langan.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    existing = await repo.get_user(session, uid)
    if existing and existing.phone_normalized and existing.phone_normalized != phone:
        await message.answer("❌ Raqamni o'zgartirib bo'lmaydi.")
        return

    await repo.set_user_flags(session, uid, phone_normalized=phone)

    await message.answer("✅ Raqam qabul qilindi.", reply_markup=ReplyKeyboardRemove())
    await enter_voting_stage(message, session, state, uid, message.bot)
