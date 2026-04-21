"""REQUIRED_CHANNEL_ID bo'yicha kanal taklif havolasi (getChat / createChatInviteLink)."""

from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from config import get_settings

logger = logging.getLogger(__name__)

_cached_url: Optional[str] = None
_cached_for: Optional[str] = None


async def get_required_channel_join_url(bot: Bot, *, force_refresh: bool = False) -> str:
    """
    Kanalga o'tish uchun havola.

    1) get_chat().invite_link (asosiy taklif havolasi, agar mavjud bo'lsa)
    2) create_chat_invite_link — qo'shimcha havola (asosiyni bekor qilmaydi)
    3) export_chat_invite_link — oxirgi variant (Telegram qoidasiga ko'ra asosiy havola yangilanishi mumkin)
    4) ochiq kanal: https://t.me/username
    """
    global _cached_url, _cached_for

    settings = get_settings()
    raw = (settings.required_channel_id or "").strip()
    if not raw:
        logger.error("required_channel_id bo'sh")
        return "https://t.me/telegram"

    if _cached_for != raw:
        _cached_url = None
        _cached_for = raw

    if not force_refresh and _cached_url:
        return _cached_url

    chat = None
    try:
        chat = await bot.get_chat(raw)
    except TelegramBadRequest as e:
        logger.error("get_chat(%s) xato: %s", raw, e)
        if raw.startswith("@"):
            u = f"https://t.me/{raw[1:]}"
            _cached_url = u
            return u
        raise

    if getattr(chat, "invite_link", None):
        _cached_url = chat.invite_link
        return chat.invite_link

    try:
        inv = await bot.create_chat_invite_link(chat_id=raw, name="sorovnomabot")
        url = inv.invite_link
        _cached_url = url
        logger.info("Kanal uchun qo'shimcha taklif havolasi yaratildi.")
        return url
    except TelegramBadRequest as e:
        logger.warning("create_chat_invite_link: %s", e)

    try:
        url = await bot.export_chat_invite_link(chat_id=raw)
        _cached_url = url
        logger.warning("export_chat_invite_link ishlatildi (asosiy taklif havolasi yangilanishi mumkin).")
        return url
    except TelegramBadRequest as e:
        logger.warning("export_chat_invite_link: %s", e)

    if getattr(chat, "username", None):
        u = f"https://t.me/{chat.username}"
        _cached_url = u
        return u

    logger.error("Kanal uchun taklif havolasi olinmadi: %s", raw)
    if raw.startswith("@"):
        u = f"https://t.me/{raw[1:]}"
        _cached_url = u
        return u
    raise RuntimeError(
        "Kanal taklif havolasini olish uchun botni kanal admini qiling "
        "(«Foydalanuvchilarni qo'shish» huquqi) yoki REQUIRED_CHANNEL_ID ni @username qilib ko'ring."
    )


async def preload_required_channel_join_url(bot: Bot) -> None:
    """Ishga tushganda bir marta — birinchi /start tezroq bo'ladi."""
    try:
        await get_required_channel_join_url(bot)
    except Exception as e:
        logger.warning("Kanal taklif havolasi oldindan yuklanmadi: %s", e)


_cached_group_url: Optional[str] = None
_cached_group_for: Optional[str] = None


async def get_required_group_join_url(bot: Bot, *, force_refresh: bool = False) -> str | None:
    """Guruh taklif havolasi (agar REQUIRED_GROUP_* sozlangan bo'lsa).

    Avval `.env` dagi `REQUIRED_GROUP_JOIN_URL` ishlatiladi; bo'lmasa
    `REQUIRED_GROUP_ID` uchun `get_chat().invite_link` yoki `create_chat_invite_link`
    orqali havola olinadi. Hech biri bo'lmasa — `None`.
    """
    global _cached_group_url, _cached_group_for

    settings = get_settings()
    env_url = (settings.required_group_join_url or "").strip()
    if env_url:
        return env_url

    gid = (settings.required_group_id or "").strip()
    if not gid:
        return None

    if _cached_group_for != gid:
        _cached_group_url = None
        _cached_group_for = gid

    if not force_refresh and _cached_group_url:
        return _cached_group_url

    try:
        chat = await bot.get_chat(gid)
    except TelegramBadRequest as e:
        logger.warning("Guruh get_chat(%s) xato: %s", gid, e)
        if gid.startswith("@"):
            u = f"https://t.me/{gid[1:]}"
            _cached_group_url = u
            return u
        return None

    if getattr(chat, "invite_link", None):
        _cached_group_url = chat.invite_link
        return chat.invite_link

    try:
        inv = await bot.create_chat_invite_link(chat_id=gid, name="sorovnomabot-group")
        _cached_group_url = inv.invite_link
        return inv.invite_link
    except TelegramBadRequest as e:
        logger.warning("Guruh create_chat_invite_link: %s", e)

    if getattr(chat, "username", None):
        u = f"https://t.me/{chat.username}"
        _cached_group_url = u
        return u
    return None
