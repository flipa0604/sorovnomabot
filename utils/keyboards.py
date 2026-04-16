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
            [InlineKeyboardButton(text="📢 Kanalga o'tish", url=link)]
            [InlineKeyboardButton(text="✅ A'zolikni tekshirish", callback_data="sub:check")]
        ],
    )


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
