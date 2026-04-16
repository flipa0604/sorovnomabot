from datetime import date, datetime, timedelta, timezone

from sqlalchemy import String, and_, cast, exists, func, or_, select, true
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


async def get_user_vote(
    session: AsyncSession,
    telegram_id: int,
) -> Vote | None:
    """Foydalanuvchining (agar bor bo'lsa) yagona ovoz yozuvi; direktor yuklangan."""
    result = await session.execute(
        select(Vote)
        .options(selectinload(Vote.director).selectinload(Director.district))
        .where(Vote.user_telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def upsert_user_vote(
    session: AsyncSession,
    telegram_id: int,
    director_id: int,
) -> Vote:
    """Ovoz bo'lmasa yaratadi, bo'lsa direktor_id ni yangilaydi."""
    existing = await get_user_vote(session, telegram_id)
    if existing:
        existing.director_id = director_id
        await session.flush()
        return existing
    v = Vote(user_telegram_id=telegram_id, director_id=director_id)
    session.add(v)
    await session.flush()
    return v


async def create_vote(
    session: AsyncSession,
    telegram_id: int,
    director_id: int,
) -> Vote:
    vote = Vote(
        user_telegram_id=telegram_id,
        director_id=director_id,
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


async def count_directors_in_district(session: AsyncSession, district_id: int) -> int:
    n = await session.scalar(
        select(func.count()).select_from(Director).where(Director.district_id == district_id)
    )
    return int(n or 0)


async def list_directors_by_district_school_page(
    session: AsyncSession,
    district_id: int,
    page: int,
    per_page: int = 20,
) -> list[Director]:
    """Maktab nomi bo'yicha tartib; sahifalash."""
    stmt = (
        select(Director)
        .options(selectinload(Director.district))
        .where(Director.district_id == district_id)
        .order_by(Director.school_name, Director.id)
        .offset(max(0, page) * per_page)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


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


# --- Web admin: statistika va jadvallar ---


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_complete_expr():
    return and_(
        User.channel_ok.is_(True),
        User.instagram_ok.is_(True),
        User.phone_normalized.isnot(None),
    )


async def admin_count_users(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(User)) or 0)


async def admin_count_votes(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Vote)) or 0)


async def admin_count_users_since(session: AsyncSession, since: datetime) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(User).where(User.created_at >= since)) or 0
    )


async def admin_count_votes_since(session: AsyncSession, since: datetime) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(Vote).where(Vote.created_at >= since)) or 0
    )


async def admin_count_users_complete(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(User).where(_user_complete_expr())) or 0
    )


async def admin_count_users_voted(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Vote)) or 0)


async def admin_count_complete_without_vote(session: AsyncSession) -> int:
    """To'liq ro'yxatdan o'tgan, lekin hali ovoz bermagan."""
    vote_exists = exists().where(Vote.user_telegram_id == User.telegram_id)
    return int(
        await session.scalar(
            select(func.count()).select_from(User).where(_user_complete_expr(), ~vote_exists)
        )
        or 0
    )


async def admin_dashboard_bundle(session: AsyncSession) -> dict:
    """Bosh sahifa uchun yig'ilgan statistikalar."""
    now = _utcnow()
    total_users = await admin_count_users(session)
    total_votes = await admin_count_votes(session)
    users_24h = await admin_count_users_since(session, now - timedelta(hours=24))
    users_7d = await admin_count_users_since(session, now - timedelta(days=7))
    users_30d = await admin_count_users_since(session, now - timedelta(days=30))
    votes_24h = await admin_count_votes_since(session, now - timedelta(hours=24))
    votes_7d = await admin_count_votes_since(session, now - timedelta(days=7))
    votes_30d = await admin_count_votes_since(session, now - timedelta(days=30))
    users_complete = await admin_count_users_complete(session)
    users_voted = await admin_count_users_voted(session)
    no_vote = await admin_count_complete_without_vote(session)
    incomplete = max(0, total_users - users_complete)
    top = await admin_top_directors(session, 10)
    users_series, votes_series = await admin_daily_counts(session, days=7)
    return {
        "total_users": total_users,
        "total_votes": total_votes,
        "users_24h": users_24h,
        "users_7d": users_7d,
        "users_30d": users_30d,
        "votes_24h": votes_24h,
        "votes_7d": votes_7d,
        "votes_30d": votes_30d,
        "users_complete": users_complete,
        "users_voted": users_voted,
        "users_no_vote": no_vote,
        "users_incomplete": incomplete,
        "top_directors": top,
        "chart_users": users_series,
        "chart_votes": votes_series,
    }


async def admin_top_directors(session: AsyncSession, limit: int = 10) -> list[tuple[Director, int]]:
    rows = await directors_with_vote_counts(session)
    rows = [(d, c) for d, c in rows if c > 0]
    rows.sort(key=lambda x: (-x[1], x[0].sort_order, x[0].full_name or ""))
    return rows[:limit]


def _day_key(raw) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return date.fromisoformat(raw[:10])
    return None


async def admin_daily_counts(
    session: AsyncSession,
    *,
    days: int = 7,
) -> tuple[list[tuple[date, int]], list[tuple[date, int]]]:
    """Oxirgi `days` kun (UTC, kalendarda) bo'yicha yangi foydalanuvchilar va ovozlar."""
    today = _utcnow().date()
    start = today - timedelta(days=days - 1)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)

    u_stmt = (
        select(func.date(User.created_at), func.count())
        .where(User.created_at >= start_dt)
        .group_by(func.date(User.created_at))
    )
    v_stmt = (
        select(func.date(Vote.created_at), func.count())
        .where(Vote.created_at >= start_dt)
        .group_by(func.date(Vote.created_at))
    )
    u_rows: dict[date, int] = {}
    for r in (await session.execute(u_stmt)).all():
        dk = _day_key(r[0])
        if dk:
            u_rows[dk] = int(r[1])
    v_rows: dict[date, int] = {}
    for r in (await session.execute(v_stmt)).all():
        dk = _day_key(r[0])
        if dk:
            v_rows[dk] = int(r[1])

    labels: list[date] = [start + timedelta(days=i) for i in range(days)]
    users_series = [(d, u_rows.get(d, 0)) for d in labels]
    votes_series = [(d, v_rows.get(d, 0)) for d in labels]
    return users_series, votes_series


async def admin_districts_with_school_counts(session: AsyncSession) -> list[tuple[District, int]]:
    cnt = func.count(Director.id).label("n")
    stmt = (
        select(District, cnt)
        .outerjoin(Director, Director.district_id == District.id)
        .group_by(District.id)
        .order_by(District.sort_order, District.name)
    )
    rows = (await session.execute(stmt)).all()
    return [(r[0], int(r[1])) for r in rows]


async def admin_list_directors_in_district(
    session: AsyncSession,
    district_id: int,
) -> list[tuple[Director, int]]:
    cnt = func.count(Vote.id).label("vote_count")
    stmt = (
        select(Director, cnt)
        .options(selectinload(Director.district))
        .outerjoin(Vote, Vote.director_id == Director.id)
        .where(Director.district_id == district_id)
        .group_by(Director.id)
        .order_by(Director.school_name, Director.id)
    )
    rows = (await session.execute(stmt)).all()
    return [(r[0], int(r[1])) for r in rows]


async def admin_list_directors_for_dropdown(session: AsyncSession) -> list[Director]:
    """Foydalanuvchilar filtri uchun direktorlar ro'yxati."""
    stmt = (
        select(Director)
        .options(selectinload(Director.district))
        .order_by(Director.district_id, Director.school_name, Director.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def admin_list_users_page(
    session: AsyncSession,
    *,
    search: str | None,
    status: str,
    sort: str,
    order: str,
    page: int,
    per_page: int = 30,
    director_id: int | None = None,
) -> tuple[list[User], int]:
    """status: all | complete | voted | no_vote | incomplete; director_id — shu direktorga ovoz berganlar."""
    stmt = select(User).options(
        selectinload(User.vote).selectinload(Vote.director).selectinload(Director.district)
    )
    count_base = select(func.count()).select_from(User)

    vote_exists = exists().where(Vote.user_telegram_id == User.telegram_id)

    if director_id is not None:
        voted_for_dir = exists().where(
            Vote.user_telegram_id == User.telegram_id,
            Vote.director_id == director_id,
        )
        stmt = stmt.where(voted_for_dir)
        count_base = count_base.where(voted_for_dir)

    if status == "complete":
        stmt = stmt.where(_user_complete_expr())
        count_base = count_base.where(_user_complete_expr())
    elif status == "voted":
        stmt = stmt.where(vote_exists)
        count_base = count_base.where(vote_exists)
    elif status == "no_vote":
        stmt = stmt.where(_user_complete_expr(), ~vote_exists)
        count_base = count_base.where(_user_complete_expr(), ~vote_exists)
    elif status == "incomplete":
        stmt = stmt.where(~_user_complete_expr())
        count_base = count_base.where(~_user_complete_expr())

    q = (search or "").strip()
    if q:
        like = f"%{q}%"
        cond = or_(
            User.username.ilike(like),
            User.full_name.ilike(like),
            User.phone_normalized.ilike(like),
            cast(User.telegram_id, String).ilike(like),
        )
        stmt = stmt.where(cond)
        count_base = count_base.where(cond)

    sort_map = {
        "created_at": User.created_at,
        "telegram_id": User.telegram_id,
        "full_name": User.full_name,
        "username": User.username,
    }
    col = sort_map.get(sort, User.created_at)
    if order.lower() == "asc":
        stmt = stmt.order_by(col.asc(), User.telegram_id.asc())
    else:
        stmt = stmt.order_by(col.desc(), User.telegram_id.desc())

    total = int((await session.execute(count_base)).scalar_one() or 0)
    page = max(0, page)
    stmt = stmt.offset(page * per_page).limit(per_page)
    rows = list((await session.execute(stmt)).scalars().all())
    return rows, total


async def admin_list_directors_page(
    session: AsyncSession,
    *,
    district_id: int | None,
    search: str | None,
    sort: str,
    order: str,
    page: int,
    per_page: int = 25,
) -> tuple[list[tuple[Director, int]], int]:
    conditions = []
    if district_id is not None:
        conditions.append(Director.district_id == district_id)
    q = (search or "").strip()
    if q:
        like = f"%{q}%"
        conditions.append(or_(Director.school_name.ilike(like), Director.full_name.ilike(like)))
    where_clause = and_(*conditions) if conditions else true()

    total = int(await session.scalar(select(func.count()).select_from(Director).where(where_clause)) or 0)

    vc = func.count(Vote.id).label("vc")
    stmt = (
        select(Director, vc)
        .options(selectinload(Director.district))
        .outerjoin(Vote, Vote.director_id == Director.id)
        .where(where_clause)
        .group_by(Director.id)
    )

    sort_key = sort or "vote_count"
    desc = order.lower() != "asc"
    if sort_key == "school_name":
        ob = Director.school_name.desc() if desc else Director.school_name.asc()
    elif sort_key == "full_name":
        ob = Director.full_name.desc() if desc else Director.full_name.asc()
    elif sort_key == "sort_order":
        ob = Director.sort_order.desc() if desc else Director.sort_order.asc()
    elif sort_key == "district":
        ob = Director.district_id.desc() if desc else Director.district_id.asc()
    else:
        ob = vc.desc() if desc else vc.asc()

    stmt = stmt.order_by(ob, Director.id.asc())
    page = max(0, page)
    stmt = stmt.offset(page * per_page).limit(per_page)
    rows = (await session.execute(stmt)).all()
    return [(r[0], int(r[1])) for r in rows], total
