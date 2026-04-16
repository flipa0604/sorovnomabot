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
                    text="✅ Ko'rdim",
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
            [InlineKeyboardButton(text="📢 Kanal", url=link)],
            [InlineKeyboardButton(text="✅ A'zolikni tekshirish", callback_data="sub:check")],
        ],
    )


def vote_start_deeplink_url(bot_username: str, director_id: int) -> str:
    """Tashqi ulashuvlar uchun: t.me/Bot?start=d{id}"""
    u = bot_username.lstrip("@")
    return f"https://t.me/{u}?start=d{director_id}"


def director_detail_keyboard(
    director_id: int,
    district_id: int,
    list_page: int,
) -> InlineKeyboardMarkup:
    """Batafsil: ovoz (callback), inline ulashish, ro'yxatga."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ovoz berish", callback_data=f"vok:{director_id}")],
            [
                InlineKeyboardButton(
                    text="📤 Ulashish",
                    switch_inline_query=f"d{director_id}",
                )
            ],
            [InlineKeyboardButton(text="🔙 Ro'yxatga", callback_data=f"pg:{district_id}:{list_page}")],
        ]
    )


def schools_page_keyboard(
    directors: list,
    district_id: int,
    page: int,
    total_count: int,
    per_page: int = 20,
) -> InlineKeyboardMarkup:
    """Maktab tugmalari + sahifa (20 tadan) + boshqa tuman."""
    rows: list[list[InlineKeyboardButton]] = []
    for dr in directors:
        label = (dr.school_name or "").strip()[:60] or f"#{dr.id}"
        rows.append(
            [InlineKeyboardButton(text=f"🏫 {label}", callback_data=f"dt:{dr.id}:{district_id}:{page}")]
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
