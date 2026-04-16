import io
import logging
from datetime import datetime, timezone

import pandas as pd
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from database import repositories as repo
from filters.admin import AdminFilter

logger = logging.getLogger(__name__)
router = Router(name="admin")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")


@router.message(Command("admin"), AdminFilter())
async def cmd_admin(message: Message) -> None:
    await message.answer(
        "Admin buyruqlar:\n"
        "/stats — ovozlar soni va TOP natijalar (yangilash uchun qayta yuboring)\n"
        "/export — barcha ovozlar Excel fayli (pandas)\n"
    )


@router.message(Command("stats"), AdminFilter())
async def cmd_stats(message: Message, session) -> None:
    total, top = await repo.stats_summary(session)
    lines = [f"Jami ovozlar: <b>{total}</b>", ""]
    if not top:
        lines.append("Hali ovoz yo'q.")
    else:
        lines.append("TOP (direktor — maktab — tuman — ovozlar):")
        for i, (name, cnt, school, tuman) in enumerate(top[:50], 1):
            lines.append(f"{i}. {name} — {school} ({tuman}) — <b>{cnt}</b>")
    await message.answer("\n".join(lines))


@router.message(Command("export"), AdminFilter())
async def cmd_export(message: Message, session) -> None:
    votes = await repo.votes_for_export(session)
    rows = []
    for v in votes:
        u = v.user
        d = v.director
        rows.append(
            {
                "vote_id": v.id,
                "voted_at_utc": v.created_at.isoformat() if v.created_at else "",
                "telegram_id": v.user_telegram_id,
                "username": u.username if u else "",
                "tg_full_name": u.full_name if u else "",
                "phone_normalized": u.phone_normalized if u else "",
                "director_id": d.id if d else "",
                "director_name": d.full_name if d else "",
                "district": d.district.name if d and d.district else "",
                "school": d.school_name if d else "",
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
        caption="Ovozlar eksporti (pandas/openpyxl).",
    )
