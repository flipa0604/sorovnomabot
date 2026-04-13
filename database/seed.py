"""Birinchi ishga tushganda: Buxoro tumanlari va ixtiyoriy CSV dan direktorlar."""

import csv
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Director, District

logger = logging.getLogger(__name__)

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "directors_import.csv"

# Buxoro viloyati tumanlari (so'rovnoma faqat shu hududda)
BUXORO_DISTRICTS: list[tuple[str, str, int]] = [
    ("buxoro_sh", "Buxoro shahri", 1),
    ("buxoro_t", "Buxoro tumani", 2),
    ("gijduvon", "G'ijduvon tumani", 3),
    ("jondor", "Jondor tumani", 4),
    ("kogon", "Kogon tumani", 5),
    ("kogon_sh", "Kogon shahri", 6),
    ("olot", "Olot tumani", 7),
    ("peshku", "Peshku tumani", 8),
    ("qorakol", "Qorako'l tumani", 9),
    ("qorovulbazar", "Qorovulbazar tumani", 10),
    ("romitan", "Romitan tumani", 11),
    ("shofirkon", "Shofirkon tumani", 12),
    ("vobkent", "Vobkent tumani", 13),
]


async def seed_districts_if_empty(session: AsyncSession) -> int:
    n = await session.scalar(select(func.count()).select_from(District))
    if n and int(n) > 0:
        return 0
    inserted = 0
    for code, name, order in BUXORO_DISTRICTS:
        session.add(District(code=code, name=name, sort_order=order))
        inserted += 1
    await session.flush()
    logger.info("Buxoro tumanlari: %s ta qo'shildi.", inserted)
    return inserted


async def seed_directors_from_csv_if_empty(session: AsyncSession) -> int:
    n = await session.scalar(select(func.count()).select_from(Director))
    if n and int(n) > 0:
        return 0
    if not CSV_PATH.exists():
        logger.warning("CSV topilmadi: %s — direktorlar web-admin orqali kiritiladi.", CSV_PATH)
        return 0

    districts_by_code: dict[str, District] = {}
    res = await session.execute(select(District))
    for d in res.scalars().all():
        districts_by_code[d.code] = d

    inserted = 0
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            full_name = (row.get("full_name") or "").strip()
            school_name = (row.get("school_name") or "").strip()
            district_code = (row.get("district_code") or "").strip()
            if not full_name or not school_name or not district_code:
                continue
            dist = districts_by_code.get(district_code)
            if not dist:
                logger.warning("CSV: tuman kodi '%s' topilmadi, qator o'tkazib yuborildi.", district_code)
                continue
            dr = Director(
                district_id=dist.id,
                full_name=full_name,
                school_name=school_name,
                sort_order=int(row.get("sort_order") or 0),
            )
            session.add(dr)
            inserted += 1
    await session.flush()
    if inserted:
        logger.info("CSV dan %s ta direktor yuklandi.", inserted)
    return inserted
