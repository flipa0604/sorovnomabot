import html
import io
import logging
from datetime import datetime, timezone

import pandas as pd
from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from config import get_settings
from database import repositories as repo
from filters.admin import AdminFilter

logger = logging.getLogger(__name__)
router = Router(name="admin")

TG_MSG_LIMIT = 4000


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")


def _split_html_message(text: str, limit: int = TG_MSG_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return parts


@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message) -> None:
    settings = get_settings()
    base = (settings.web_admin_public_url or "").strip().rstrip("/")
    kb: InlineKeyboardMarkup | None = None
    if base and (base.startswith("https://") or base.startswith("http://")):
        mini_url = f"{base}/tg-app"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🖥 Admin panel (Web App)", web_app=WebAppInfo(url=mini_url))]
            ]
        )

    text = (
        "<b>Admin buyruqlari</b>\n\n"
        "<b>/stats</b> — umumiy statistika:\n"
        "• barcha Telegram foydalanuvchilar soni\n"
        "• jami berilgan ovozlar\n"
        "• tumanlar va maktab direktorlari soni\n"
        "• har bir tuman bo'yicha: maktablar soni va shu tumanga tushgan ovozlar\n\n"
        "<b>/top</b> — ovozlar soni bo'yicha <b>TOP-10</b> maktab direktorlari (reyting).\n\n"
        "<b>/export</b> — barcha ovozlar Excel fayl ko'rinishida (pandas).\n\n"
        "<b>/admin</b> — ushbu yordam xabari."
    )
    chunks = _split_html_message(text)
    for i, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            parse_mode=ParseMode.HTML,
            reply_markup=kb if i == 0 else None,
        )


@router.message(Command("stats"), AdminFilter())
async def cmd_stats(message: Message, session) -> None:
    total_users = await repo.admin_count_users(session)
    total_votes = await repo.admin_count_votes(session)
    n_directors = await repo.admin_count_directors_total(session)
    n_districts = await repo.admin_count_districts_total(session)
    district_rows = await repo.admin_district_stats_for_bot(session)

    lines = [
        "<b>Statistika</b>",
        "",
        f"🗺 Tumanlar: <b>{n_districts}</b>",
        f"🏫 Maktab direktorlari: <b>{n_directors}</b>",
        f"👥 Foydalanuvchilar (botda): <b>{total_users}</b>",
        f"🗳 Jami ovozlar: <b>{total_votes}</b>",
        "",
        "<b>Tumanlar bo'yicha</b>",
        "<i>(maktablar — shu tumanga tushgan ovozlar)</i>",
    ]
    for name, schools, votes in district_rows:
        lines.append(
            f"• {html.escape(name)} — <b>{schools}</b> maktab, <b>{votes}</b> ovoz"
        )
    text = "\n".join(lines)
    for chunk in _split_html_message(text):
        await message.answer(chunk, parse_mode=ParseMode.HTML)


@router.message(Command("top"), AdminFilter())
async def cmd_top(message: Message, session) -> None:
    top = await repo.admin_top_directors(session, 10)
    if not top:
        await message.answer("Hali hech qayerga ovoz berilmagan yoki TOP bo'sh.", parse_mode=ParseMode.HTML)
        return
    lines = ["<b>TOP-10</b> <i>(ovozlar soni bo'yicha)</i>", ""]
    for i, (d, cnt) in enumerate(top, 1):
        tuman = html.escape(d.district.name) if d.district else "—"
        lines.append(
            f"{i}. <b>{html.escape(d.full_name or '')}</b>\n"
            f"   🏫 {html.escape(d.school_name or '')}\n"
            f"   📍 {tuman} — <b>{cnt}</b> ovoz"
        )
    text = "\n".join(lines)
    for chunk in _split_html_message(text):
        await message.answer(chunk)


@router.message(Command("export"), AdminFilter())
async def cmd_export(message: Message, session) -> None:
    votes = await repo.votes_for_export(session)
    rows = []
    for v in votes:
        u = v.user
        d = v.director
        rows.append(
            {
                "Id": v.id,
                "Sana/vaqt": v.created_at.isoformat() if v.created_at else "",
                "Telegram_id": v.user_telegram_id,
                "Foydalanuvchi": u.full_name if u else "",
                "Username": u.username if u else "",
                "Telefon": u.phone_normalized if u else "",
                "Direktor id": d.id if d else "",
                "Direktor": d.full_name if d else "",
                "Tuman": d.district.name if d and d.district else "",
                "Maktab": d.school_name if d else "",
            }
        )
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="votes")
    buf.seek(0)
    fname = f"ovozlar_{_now_iso()}.xlsx"
    await message.answer_document(
        BufferedInputFile(buf.getvalue(), filename=fname),
        caption="Ovozlar eksporti.",
    )
