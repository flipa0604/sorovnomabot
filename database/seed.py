"""Birinchi ishga tushganda: Buxoro tumanlari va ixtiyoriy CSV dan maktablar."""

import csv
import logging
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import District, School

logger = logging.getLogger(__name__)

CSV_PRIMARY = Path(__file__).resolve().parent.parent / "data" / "schools.csv"
CSV_ALTERNATES = (
    Path(__file__).resolve().parent.parent / "data" / "schools_import.csv",
    Path(__file__).resolve().parent.parent / "data" / "directors_import.csv",
)

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


def _csv_path() -> Path | None:
    if CSV_PRIMARY.exists():
        return CSV_PRIMARY
    for p in CSV_ALTERNATES:
        if p.exists():
            return p
    return None


def _detect_csv_delimiter(first_nonempty_line: str) -> str:
    """Excel/O‘zbek CSV ko‘pincha ';' bilan; DictReader standart ','."""
    line = first_nonempty_line.strip()
    if not line:
        return ","
    semi = line.count(";")
    comma = line.count(",")
    if semi > 0 and semi >= comma:
        return ";"
    return ","


def _normalize_row_keys(row: dict[str, str]) -> dict[str, str]:
    """Bom yoki bo'sh joy bilan kelgan ustun nomlarini school_name / district_code ga yaqinlashtirish."""
    out: dict[str, str] = {}
    for k, v in row.items():
        if k is None:
            continue
        key = k.strip().lower().replace("\ufeff", "")
        out[key] = v
    # keng tarqalgan sinonimlar
    aliases = {
        "maktab": "school_name",
        "maktab_nomi": "school_name",
        "name": "school_name",
        "tuman_kodi": "district_code",
        "region_code": "district_code",
        "kod": "district_code",
    }
    merged = dict(out)
    for old, new in aliases.items():
        if old in merged and new not in merged:
            merged[new] = merged[old]
    return merged


async def seed_schools_from_csv_if_empty(session: AsyncSession) -> int:
    n = await session.scalar(select(func.count()).select_from(School))
    if n and int(n) > 0:
        return 0
    path = _csv_path()
    if not path:
        logger.warning(
            "CSV topilmadi (kutilgan: %s yoki %s) — maktablar web-admin orqali kiritiladi.",
            CSV_PRIMARY,
            CSV_ALTERNATES[0],
        )
        return 0

    districts_by_code: dict[str, District] = {}
    res = await session.execute(select(District))
    for d in res.scalars().all():
        districts_by_code[d.code] = d

    inserted = 0
    skipped_no_dist = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        first = ""
        pos = f.tell()
        for raw in f:
            if raw.strip():
                first = raw
                break
        f.seek(pos)
        delim = _detect_csv_delimiter(first)
        reader = csv.DictReader(f, delimiter=delim)
        for row in reader:
            row = _normalize_row_keys({k or "": (v or "") for k, v in row.items()})
            school_name = (row.get("school_name") or "").strip()
            district_code = (row.get("district_code") or "").strip()
            if not school_name or not district_code:
                continue
            dist = districts_by_code.get(district_code)
            if not dist:
                skipped_no_dist += 1
                logger.warning("CSV: tuman kodi '%s' topilmadi, qator o'tkazib yuborildi.", district_code)
                continue
            sch = School(
                district_id=dist.id,
                school_name=school_name,
                sort_order=int(row.get("sort_order") or 0),
            )
            session.add(sch)
            inserted += 1
    await session.flush()
    if inserted:
        logger.info("CSV dan %s ta maktab yuklandi (%s, delimiter=%r).", inserted, path.name, delim)
    elif path.stat().st_size > 10:
        logger.warning(
            "CSV fayl bor (%s) lekin 0 ta import — delimiter (; yoki ,), ustunlar "
            "(school_name, district_code) yoki tuman kodlari seed bilan mosligini tekshiring.",
            path.name,
        )
    return inserted
