from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Director, District, User, Vote


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    full_name: str | None,
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.username = username
        user.full_name = full_name
        return user
    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
    )
    session.add(user)
    await session.flush()
    return user


async def set_user_flags(
    session: AsyncSession,
    telegram_id: int,
    *,
    channel_ok: bool | None = None,
    instagram_ok: bool | None = None,
    phone_normalized: str | None = None,
) -> None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        return
    if channel_ok is not None:
        user.channel_ok = channel_ok
    if instagram_ok is not None:
        user.instagram_ok = instagram_ok
    if phone_normalized is not None:
        user.phone_normalized = phone_normalized


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def phone_taken_by_other(session: AsyncSession, phone_normalized: str, telegram_id: int) -> bool:
    result = await session.execute(
        select(User.telegram_id).where(
            User.phone_normalized == phone_normalized,
            User.telegram_id != telegram_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def has_voted_by_telegram(session: AsyncSession, telegram_id: int) -> bool:
    result = await session.execute(select(Vote.id).where(Vote.user_telegram_id == telegram_id))
    return result.scalar_one_or_none() is not None


async def has_voted_by_phone(session: AsyncSession, phone_normalized: str) -> bool:
    result = await session.execute(select(Vote.id).where(Vote.phone_normalized == phone_normalized))
    return result.scalar_one_or_none() is not None


async def create_vote(
    session: AsyncSession,
    telegram_id: int,
    director_id: int,
    phone_normalized: str,
) -> Vote:
    vote = Vote(
        user_telegram_id=telegram_id,
        director_id=director_id,
        phone_normalized=phone_normalized,
    )
    session.add(vote)
    await session.flush()
    return vote


async def list_districts(session: AsyncSession) -> list[District]:
    stmt = select(District).order_by(District.sort_order, District.name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_district(session: AsyncSession, district_id: int) -> District | None:
    result = await session.execute(select(District).where(District.id == district_id))
    return result.scalar_one_or_none()


async def search_directors(
    session: AsyncSession,
    query: str,
    district_id: int | None,
    limit: int = 50,
) -> list[Director]:
    stmt = (
        select(Director)
        .options(selectinload(Director.district))
        .order_by(Director.sort_order, Director.full_name)
    )
    if district_id is not None:
        stmt = stmt.where(Director.district_id == district_id)
    q = query.strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Director.full_name.ilike(like))
    stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_director(session: AsyncSession, director_id: int) -> Director | None:
    result = await session.execute(
        select(Director)
        .options(selectinload(Director.district))
        .where(Director.id == director_id)
    )
    return result.scalar_one_or_none()


async def stats_summary(session: AsyncSession) -> tuple[int, list[tuple[str, int, str, str]]]:
    total = await session.scalar(select(func.count()).select_from(Vote))
    total = int(total or 0)

    stmt = (
        select(Director.full_name, Director.school_name, District.name, func.count(Vote.id))
        .join(Vote, Vote.director_id == Director.id)
        .join(District, Director.district_id == District.id)
        .group_by(Director.id)
        .order_by(func.count(Vote.id).desc())
    )
    rows = (await session.execute(stmt)).all()
    top: list[tuple[str, int, str, str]] = [
        (r[0], int(r[3]), r[1], r[2]) for r in rows
    ]
    return total, top


async def votes_for_export(session: AsyncSession) -> list[Vote]:
    stmt = (
        select(Vote)
        .options(selectinload(Vote.director).selectinload(Director.district), selectinload(Vote.user))
        .order_by(Vote.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def directors_with_vote_counts(session: AsyncSession) -> list[tuple[Director, int]]:
    cnt = func.count(Vote.id).label("vote_count")
    stmt = (
        select(Director, cnt)
        .options(selectinload(Director.district))
        .outerjoin(Vote, Vote.director_id == Director.id)
        .group_by(Director.id)
        .order_by(cnt.desc(), Director.sort_order, Director.full_name)
    )
    rows = (await session.execute(stmt)).all()
    return [(r[0], int(r[1])) for r in rows]


async def count_votes_for_director(session: AsyncSession, director_id: int) -> int:
    n = await session.scalar(select(func.count()).select_from(Vote).where(Vote.director_id == director_id))
    return int(n or 0)


async def create_district(session: AsyncSession, code: str, name: str, sort_order: int = 0) -> District:
    d = District(code=code.strip(), name=name.strip(), sort_order=sort_order)
    session.add(d)
    await session.flush()
    return d


async def update_district(
    session: AsyncSession,
    district_id: int,
    *,
    code: str | None = None,
    name: str | None = None,
    sort_order: int | None = None,
) -> District | None:
    d = await get_district(session, district_id)
    if not d:
        return None
    if code is not None:
        d.code = code.strip()
    if name is not None:
        d.name = name.strip()
    if sort_order is not None:
        d.sort_order = sort_order
    await session.flush()
    return d


async def delete_district(session: AsyncSession, district_id: int) -> bool:
    d = await get_district(session, district_id)
    if not d:
        return False
    n = await session.scalar(
        select(func.count()).select_from(Director).where(Director.district_id == district_id)
    )
    if int(n or 0) > 0:
        return False
    await session.delete(d)
    await session.flush()
    return True


async def create_director(
    session: AsyncSession,
    district_id: int,
    full_name: str,
    school_name: str,
    sort_order: int = 0,
) -> Director:
    dr = Director(
        district_id=district_id,
        full_name=full_name.strip(),
        school_name=school_name.strip(),
        sort_order=sort_order,
    )
    session.add(dr)
    await session.flush()
    return dr


async def update_director(
    session: AsyncSession,
    director_id: int,
    *,
    district_id: int | None = None,
    full_name: str | None = None,
    school_name: str | None = None,
    sort_order: int | None = None,
) -> Director | None:
    dr = await get_director(session, director_id)
    if not dr:
        return None
    if district_id is not None:
        dr.district_id = district_id
    if full_name is not None:
        dr.full_name = full_name.strip()
    if school_name is not None:
        dr.school_name = school_name.strip()
    if sort_order is not None:
        dr.sort_order = sort_order
    await session.flush()
    return dr


async def delete_director(session: AsyncSession, director_id: int) -> bool:
    dr = await get_director(session, director_id)
    if not dr:
        return False
    if await count_votes_for_director(session, director_id) > 0:
        return False
    await session.delete(dr)
    await session.flush()
    return True
