from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from database.models import District


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefonni ulashish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)


def instagram_confirm_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📷 Instagram", url=url)],
            [
                InlineKeyboardButton(
                    text="✅ Tasdiqlash",
                    callback_data="ig:confirm",
                )
            ],
        ],
    )


def _normalize_tme(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = f"https://t.me/{u.lstrip('@')}"
    return u


def channel_keyboard(join_url: str) -> InlineKeyboardMarkup:
    """join_url — kanal taklif havolasi yoki to'liq https (get_chat / create_chat_invite_link)."""
    url = _normalize_tme(join_url)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga o'tish", url=url)],
            [InlineKeyboardButton(text="✅ A'zolikni tekshirish", callback_data="sub:check")],
        ],
    )


def telegram_subscribe_keyboard(
    *,
    channel_url: str | None,
    group_url: str | None,
    need_channel: bool,
    need_group: bool,
) -> InlineKeyboardMarkup:
    """Kanal va/yoki guruh uchun yagona obuna tugmalari + «tekshirish»."""
    rows: list[list[InlineKeyboardButton]] = []
    if need_channel and channel_url:
        rows.append([InlineKeyboardButton(text="📢 Telegram kanalga o'tish", url=_normalize_tme(channel_url))])
    if need_group and group_url:
        rows.append([InlineKeyboardButton(text="👥 Telegram guruhga o'tish", url=_normalize_tme(group_url))])
    rows.append([InlineKeyboardButton(text="✅ A'zolikni tekshirish", callback_data="sub:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vote_start_deeplink_url(bot_username: str, school_id: int) -> str:
    """Tashqi ulashuvlar uchun: t.me/Bot?start=d{id}"""
    u = bot_username.lstrip("@")
    return f"https://t.me/{u}?start=d{school_id}"


def school_detail_keyboard(
    school_id: int,
    district_id: int,
    list_page: int,
) -> InlineKeyboardMarkup:
    """Batafsil: ovoz (callback), inline ulashish, ro'yxatga."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ovoz berish", callback_data=f"vok:{school_id}")],
            [
                InlineKeyboardButton(
                    text="📤 Ulashish",
                    switch_inline_query=f"d{school_id}",
                )
            ],
            [InlineKeyboardButton(text="🔙 Ro'yxatga", callback_data=f"pg:{district_id}:{list_page}")],
        ],
    )


def schools_page_keyboard(
    schools: list,
    district_id: int,
    page: int,
    total_count: int,
    per_page: int = 20,
) -> InlineKeyboardMarkup:
    """Maktab tugmalari + sahifa (20 tadan) + boshqa tuman."""
    rows: list[list[InlineKeyboardButton]] = []
    for sch in schools:
        label = (sch.school_name or "").strip()[:60] or f"#{sch.id}"
        rows.append(
            [InlineKeyboardButton(text=f"🏫 {label}", callback_data=f"dt:{sch.id}:{district_id}:{page}")]
        )

    total_pages = max(1, (total_count + per_page - 1) // per_page)
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="⏪ Oldingi",
                    callback_data=f"pg:{district_id}:{page - 1}",
                )
            )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="Keyingi ⏩",
                    callback_data=f"pg:{district_id}:{page + 1}",
                )
            )
        if nav:
            rows.append(nav)

    rows.append([InlineKeyboardButton(text="🗺 Boshqa tuman", callback_data="nav:distlist")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def district_filter_keyboard(districts: list[District]) -> InlineKeyboardMarkup:
    """Tumanlar — faqat dist:ID (barcha tumanlar yo'q)."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for d in districts:
        label = (d.name or "")[:38]
        row.append(InlineKeyboardButton(text=f"{label}", callback_data=f"dist:{d.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
