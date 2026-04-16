from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from database.models import District


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni ulashish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)


def instagram_confirm_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📷 Instagramni ochish", url=url)],
            [
                InlineKeyboardButton(
                    text="✅ Ko'rdim, keyingi qadam",
                    callback_data="ig:confirm",
                )
            ],
        ]
    )


def channel_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    """channel_username @ bilan yoki https"""
    link = channel_username if channel_username.startswith("http") else f"https://t.me/{channel_username.lstrip('@')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga o'tish", url=link)],
            [InlineKeyboardButton(text="✅ A'zolikni tekshirish", callback_data="sub:check")]
        ],
    )


def vote_start_deeplink_url(bot_username: str, director_id: int) -> str:
    """https://t.me/BotUsername?start=d123"""
    u = bot_username.lstrip("@")
    return f"https://t.me/{u}?start=d{director_id}"


def director_detail_keyboard(
    bot_username: str,
    director_id: int,
    district_id: int,
    list_page: int,
) -> InlineKeyboardMarkup:
    """Batafsil: ovoz (deeplink), inline ulashish, ro'yxatga qaytish."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗳 Ovoz berish", url=vote_start_deeplink_url(bot_username, director_id))],
            [
                InlineKeyboardButton(
                    text="📤 Ulashish",
                    switch_inline_query=f"d{director_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Ro'yxatga", callback_data=f"pg:{district_id}:{list_page}")],
        ]
    )


def schools_page_keyboard(
    directors: list,
    district_id: int,
    page: int,
    total_count: int,
    per_page: int = 20,
) -> InlineKeyboardMarkup:
    """Maktab nomi tugmalari + sahifalash."""
    rows: list[list[InlineKeyboardButton]] = []
    for dr in directors:
        label = (dr.school_name or "").strip()[:64] or f"#{dr.id}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"dt:{dr.id}:{district_id}:{page}")]
        )
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"pg:{district_id}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"pg:{district_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def district_filter_keyboard(districts: list[District]) -> InlineKeyboardMarkup:
    """Buxoro tumanlari — callback: dist:ID yoki dist:ALL."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for d in districts:
        label = d.name[:40]
        row.append(InlineKeyboardButton(text=label, callback_data=f"dist:{d.id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🌐 Barcha tumanlar", callback_data="dist:ALL")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
