import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
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
            "Hozircha tumanlar ro'yxati bo'sh. Administrator web-panel orqali tuman va maktablarni qo'shsin."
        )
        return
    await message.answer(
        "Ovoz berish boshlandi.\n\n"
        "1) Pastdagi tugmalar orqali <b>tumanni</b> tanlang.\n"
        "2) Ro'yxatdan maktabni tanlang (20 tadan sahifalanadi), batafsilda "
        "<b>Ovoz berish</b> yoki boshqa chatga <b>Ulashish</b> (inline qidiruv).\n\n"
        f"Maktab kartasini boshqa joyga yuborish: chatda <code>@{uname} d</code> + direktor ID "
        "(masalan <code>@{uname} d12</code>).\n\n"
        "Eslatma: har bir akkaunt uchun bitta ovoz saqlanadi; istalgan vaqtda boshqa direktorga "
        "<code>/start</code> yoki bot menyusidan o'zgartirishingiz mumkin. So'rovnoma Buxoro viloyati bo'yicha.",
        reply_markup=district_filter_keyboard(districts),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Bu bot maktab direktorlari o'rtasida so'rovnoma o'tkazish uchun mo'ljallangan.\n\n"
        "Jarayon: kanalga a'zolik → Instagram sahifasi → telefon → ovoz.\n"
        "Ovoz berish: tuman tanlang, ro'yxatdan maktabni tanlang; ulashish uchun inline rejim.\n\n"
        "Boshlash: /start"
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
                "Keyingi qadam: quyidagi havola orqali Instagram sahifamizni oching va "
                "tanishib chiqqaningizdan keyin «Ko'rdim» tugmasini bosing.\n\n"
                "<i>Telegram Instagramga kirishni avtomatik tekshira olmaydi — "
                "bu qadam jamoat tartibi uchun.</i>",
                reply_markup=instagram_confirm_keyboard(get_settings().instagram_profile_url),
            )
            return
        await state.set_state(Registration.wait_phone)
        await message.answer(
            "Ovoz berish uchun telefon raqamingizni ulashing (tugma orqali).",
            reply_markup=contact_keyboard(),
        )
        return

    await state.set_state(Registration.wait_subscription)
    ch = get_settings().required_channel_id
    link = ch if ch.startswith("@") else ch
    pretty = ch if ch.startswith("@") else f"kanal ({ch})"

    from utils.keyboards import channel_keyboard
    await message.answer(
        f"So'rovnomada ishtirok etish uchun avval {pretty} kanaliga a'zo bo'ling.\n"
        "Keyin «A'zolikni tekshirish» tugmasini bosing.",
        reply_markup=channel_keyboard(link if link.startswith("@") else get_settings().required_channel_id),
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
        await query.message.answer("Kanalda a'zo bo'lmaganga o'xshaysiz. Iltimos, avval kanalga qo'shiling.")
        return

    await repo.set_user_flags(session, uid, channel_ok=True)
    await state.set_state(Registration.wait_instagram)
    await query.message.answer(
        "Rahmat! Endi Instagram sahifasini oching va tanishib chiqqaningizdan keyin tugmani bosing.\n\n"
        "<i>Instagram tekshiruvi foydalanuvchi tasdiqlashi bilan amalga oshadi.</i>",
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
        "Endi ovoz berish uchun telefon raqamingizni ulashing.",
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
        await message.answer("Faqat o'z kontaktingizni yuboring.")
        return

    phone = normalize_phone(contact.phone_number or "")
    if len(phone) < 12:
        await message.answer("Telefon raqam noto'g'ri. Qaytadan yuboring.")
        return

    uid = message.from_user.id
    if await repo.phone_taken_by_other(session, phone, uid):
        await message.answer(
            "Bu telefon raqami boshqa Telegram akkauntiga bog'langan.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    existing = await repo.get_user(session, uid)
    if existing and existing.phone_normalized and existing.phone_normalized != phone:
        await message.answer("Telefon raqam o'zgartirilmaydi.")
        return

    await repo.set_user_flags(session, uid, phone_normalized=phone)

    await message.answer("Raqam qabul qilindi.", reply_markup=ReplyKeyboardRemove())
    await enter_voting_stage(message, session, state, uid, message.bot)
