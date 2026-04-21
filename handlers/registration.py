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
from utils.deeplink import parse_school_start_payload
from utils.keyboards import contact_keyboard, district_filter_keyboard, instagram_confirm_keyboard
from utils.phone import normalize_phone
from utils.states import Registration, Voting

logger = logging.getLogger(__name__)
router = Router(name="registration")


def _start_welcome_html(message: Message) -> str:
    """/start — yangi user uchun birinchi salom (HTML)."""
    fu = message.from_user
    name = (fu.first_name or fu.full_name or "Mehmon").strip()
    safe = html.escape(name)
    mention = f'<a href="tg://user?id={fu.id}">{safe}</a>'
    return (
        f"👋 <b>Assalomu alaykum</b>, {mention}!\n\n"
        "🎓 <b>BITU So'rovnoma botiga</b> <i>xush kelibsiz!</i>\n\n"
        "📍 <i>Hozirda biz</i> <b>Buxoro viloyati</b> <i>bo'yicha</i>\n"
        "🏆 <b>«Eng yaxshi maktab»</b> <i>nominatsiyasini o'tkazyapmiz.</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📲 <b>Maktablarga ovoz berish</b> <i>uchun dastlab:</i>\n\n"
        "• 📷 <b>Instagram</b> — sahifamizga <i>obuna</i> bo'ling\n"
        "• 📢 <b>Telegram kanalimizga</b> — <i>qo'shiling</i>\n\n"
        "✨ <i>Keyin esa ovoz berishingiz mumkin.</i>\n\n"
        "👇 <b>Quyidagi qadamlarni</b> bajaring — <i>biz yonindamiz!</i>"
    )


def _already_voted_html(school) -> str:
    """Foydalanuvchi avval ovoz bergan — qisqa sharaf xabari."""
    dist = school.district.name if school and school.district else ""
    sname = school.school_name if school else ""
    body = (
        "✅ <b>Siz allaqachon ovoz bergansiz!</b>\n\n"
        "🗳 <i>Tanlovingiz qabul qilingan:</i>\n\n"
        f"🏫 <b>{html.escape(sname)}</b>"
    )
    if dist:
        body += f"\n📍 <i>{html.escape(dist)}</i>"
    body += "\n\n🙏 <b>Qo'llab-quvvatlaganingiz uchun rahmat!</b>"
    return body


def _channel_prompt_html() -> str:
    return (
        "📢 <b>Telegram kanalimiz</b>\n\n"
        "💬 <i>Yangiliklar, e'lonlar va natijalardan</i> <b>birinchi bo'lib</b> "
        "<i>xabardor bo'lish uchun</i>\n"
        "👉 <b>kanalimizga obuna bo'ling.</b>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "✅ <i>Obuna bo'lgach, pastdagi</i> <b>«A'zolikni tekshirish»</b> "
        "<i>tugmasini bosing.</i>"
    )


def _channel_ok_instagram_prompt_html() -> str:
    return (
        "🎉 <b>Ajoyib!</b> <i>Telegram kanalimizga muvaffaqiyatli obuna bo'ldingiz.</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "📷 <b>Endi — Instagram sahifamiz</b>\n\n"
        "✨ <i>Bizni Instagram'da ham kuzatib boring:</i>\n"
        "🌟 <i>yangi fotolar, reellar va so'rovnomalar sizni kutmoqda.</i>\n\n"
        "👇 <b>Havolaga o'ting</b>, <i>sahifamizga</i> <b>obuna bo'ling</b>, "
        "<i>keyin</i> <b>✅ Tasdiqlash</b> <i>tugmasini bosing.</i>"
    )


def _instagram_prompt_html() -> str:
    return (
        "📷 <b>Instagram sahifamizga obuna bo'ling</b>\n\n"
        "✨ <i>Bizni Instagram'da ham kuzatib boring —</i>\n"
        "🌟 <i>yangi fotolar, reellar va qiziqarli kontent sizni kutmoqda.</i>\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "👇 <b>Havolaga o'ting</b>, <i>sahifamizga</i> <b>obuna bo'ling</b>, "
        "<i>keyin</i> <b>✅ Tasdiqlash</b> <i>tugmasini bosing.</i>"
    )


def _phone_prompt_html() -> str:
    return (
        "📱 <b>Telefon raqamingiz</b>\n\n"
        "🔐 <i>Har bir foydalanuvchi bitta marta ovoz bera olishi uchun "
        "telefon raqamingizni ulashing.</i>\n\n"
        "👇 <b>Pastdagi</b> <i>«📱 Telefonni ulashish»</i> <b>tugmasini bosing.</b>"
    )


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
        "2) Ro'yxatdan maktabni tanlang va shu maktabga ovoz bering.\n\n"
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

    existing_before = await repo.get_user(session, uid)
    is_new_user = existing_before is None

    await repo.get_or_create_user(
        session,
        uid,
        message.from_user.username,
        message.from_user.full_name,
    )

    school_id = parse_school_start_payload(command.args)

    prior_vote = await repo.get_user_vote(session, uid)
    if prior_vote and prior_vote.school and school_id is None:
        await message.answer(
            _already_voted_html(prior_vote.school),
            parse_mode=ParseMode.HTML,
        )
        return

    if is_new_user:
        await message.answer(_start_welcome_html(message), parse_mode=ParseMode.HTML)

    if await user_is_channel_member(bot, uid):
        await repo.set_user_flags(session, uid, channel_ok=True)
        u = await repo.get_user(session, uid)
        if school_id is not None and u and u.instagram_ok and u.phone_normalized:
            await offer_vote_from_start_payload(message, session, state, school_id)
            return
        if u and u.instagram_ok and u.phone_normalized:
            await enter_voting_stage(message, session, state, uid, bot)
            return
        if not u or not u.instagram_ok:
            await state.set_state(Registration.wait_instagram)
            await message.answer(
                _instagram_prompt_html(),
                reply_markup=instagram_confirm_keyboard(get_settings().instagram_profile_url),
                parse_mode=ParseMode.HTML,
            )
            return
        await state.set_state(Registration.wait_phone)
        await message.answer(
            _phone_prompt_html(),
            reply_markup=contact_keyboard(),
            parse_mode=ParseMode.HTML,
        )
        return

    await state.set_state(Registration.wait_subscription)

    from utils.channel_invite import get_required_channel_join_url
    from utils.keyboards import channel_keyboard

    ch = get_settings().required_channel_id
    try:
        join_url = await get_required_channel_join_url(bot)
    except Exception as e:
        logger.warning("Kanal taklif havolasi: %s", e)
        join_url = f"https://t.me/{ch.lstrip('@')}" if ch.startswith("@") else "https://t.me/telegram"

    await message.answer(
        _channel_prompt_html(),
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
            "⚠️ <b>Kanalda a'zolik aniqlanmadi.</b>\n\n"
            "📢 <i>Iltimos, avval</i> <b>Telegram kanalimizga obuna bo'ling</b>, "
            "<i>so'ngra qayta</i> <b>✅ A'zolikni tekshirish</b> <i>tugmasini bosing.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    await repo.set_user_flags(session, uid, channel_ok=True)
    await state.set_state(Registration.wait_instagram)
    await query.message.answer(
        _channel_ok_instagram_prompt_html(),
        reply_markup=instagram_confirm_keyboard(get_settings().instagram_profile_url),
        parse_mode=ParseMode.HTML,
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
        "🎉 <b>Zo'r!</b> <i>Instagram sahifamizga ham obuna bo'ldingiz.</i>\n\n"
        + _phone_prompt_html(),
        reply_markup=contact_keyboard(),
        parse_mode=ParseMode.HTML,
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

    await message.answer(
        "✅ <b>Raqamingiz qabul qilindi.</b>\n🙏 <i>Rahmat!</i>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.HTML,
    )
    await enter_voting_stage(message, session, state, uid, message.bot)
