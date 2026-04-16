from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from config import get_settings
from database import repositories as repo
from database.seed import seed_districts_if_empty
from database.session import async_session_maker, init_db

logger = logging.getLogger(__name__)

_TPL = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TPL))

SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _slugify(code: str) -> str:
    s = code.strip().lower().replace(" ", "_").replace("-", "_")
    s = SLUG_RE.sub("_", s).strip("_")
    return s[:64] or "tuman"


def _parse_sort_order(raw: str) -> int:
    raw = (raw or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _admin_session_ok(request: Request) -> bool:
    return bool(request.session.get("admin"))


def _flash_from_query(request: Request) -> tuple[str | None, str | None]:
    msg = request.query_params.get("msg")
    err = request.query_params.get("err")
    flash_map = {
        "district_added": "Tuman qo'shildi.",
        "district_saved": "Tuman saqlandi.",
        "district_deleted": "Tuman o'chirildi.",
        "director_added": "Maktab / direktor qo'shildi.",
        "director_saved": "Ma'lumotlar saqlandi.",
        "director_deleted": "Qator o'chirildi.",
    }
    err_map = {
        "district_has_schools": "Tumanda maktablar bor — avval ularni o'chiring yoki ko'chiring.",
        "director_has_votes": "Ovoz yig'gan direktorni o'chirib bo'lmaydi.",
    }
    return flash_map.get(msg or ""), err_map.get(err or "")


def _directors_qs_parts(
    q: str,
    district_id: int | None,
    sort: str,
    order: str,
    page: int,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if q.strip():
        items.append(("q", q.strip()))
    if district_id is not None:
        items.append(("district_id", str(district_id)))
    items.extend(
        [
            ("sort", sort),
            ("order", order),
            ("page", str(page)),
        ]
    )
    return items


def _directors_sort_urls(
    q: str,
    district_id: int | None,
    sort: str,
    order: str,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in ("school_name", "full_name", "district", "sort_order", "vote_count"):
        next_o = "asc" if (sort == col and order == "desc") else "desc"
        out[col] = urlencode(_directors_qs_parts(q, district_id, col, next_o, 0))
    return out


def _users_qs_parts(
    q: str,
    status: str,
    sort: str,
    order: str,
    page: int,
    director_id: int | None = None,
) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if q.strip():
        items.append(("q", q.strip()))
    if status and status != "all":
        items.append(("status", status))
    if director_id is not None:
        items.append(("director_id", str(director_id)))
    items.extend([("sort", sort), ("order", order), ("page", str(page))])
    return items


def _users_sort_urls(
    q: str,
    status: str,
    sort: str,
    order: str,
    director_id: int | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in ("telegram_id", "username", "full_name", "created_at"):
        next_o = "asc" if (sort == col and order == "desc") else "desc"
        out[col] = urlencode(_users_qs_parts(q, status, col, next_o, 0, director_id))
    return out


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session_maker() as s:
        n = await seed_districts_if_empty(s)
        await s.commit()
        if n:
            logger.info("Web startup: %s ta tuman seed qilindi.", n)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title="Sorovnoma admin", lifespan=lifespan)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.web_admin_secret,
        session_cookie="sorovnomabot_admin",
        same_site="lax",
        https_only=False,
    )
    return application


app = create_app()


@app.get("/login", response_class=HTMLResponse, response_model=None)
async def login_page(request: Request) -> HTMLResponse:
    if _admin_session_ok(request):
        return RedirectResponse("/", status_code=302)
    err = request.query_params.get("err")
    err_msg = None
    if err == "1":
        err_msg = "Login yoki parol noto'g'ri."
    elif err == "config":
        err_msg = "Serverda WEB_ADMIN_PASSWORD o'rnatilmagan."
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": err_msg},
    )


@app.post("/login", response_model=None)
async def login_post(
    request: Request,
    username: str = Form(),
    password: str = Form(),
) -> RedirectResponse:
    settings = get_settings()
    if not settings.web_admin_password:
        return RedirectResponse("/login?err=config", status_code=302)
    if username == settings.web_admin_username and password == settings.web_admin_password:
        request.session["admin"] = True
        return RedirectResponse("/", status_code=302)
    return RedirectResponse("/login?err=1", status_code=302)


@app.get("/logout", response_model=None)
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse, response_model=None)
async def dashboard(request: Request, session: SessionDep) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    dash = await repo.admin_dashboard_bundle(session)
    labels = [d.strftime("%d.%m.%Y") for d, _ in dash["chart_users"]]
    users_vals = [v for _, v in dash["chart_users"]]
    votes_vals = [v for _, v in dash["chart_votes"]]
    flash, flash_err = _flash_from_query(request)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "nav": "dashboard",
            "dash": dash,
            "chart_labels_json": json.dumps(labels),
            "chart_users_json": json.dumps(users_vals),
            "chart_votes_json": json.dumps(votes_vals),
            "flash": flash,
            "flash_err": flash_err,
        },
    )


@app.get("/districts", response_class=HTMLResponse, response_model=None)
async def districts_page(request: Request, session: SessionDep) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    district_rows = await repo.admin_districts_with_school_counts(session)
    flash, flash_err = _flash_from_query(request)
    return templates.TemplateResponse(
        "districts.html",
        {
            "request": request,
            "nav": "districts",
            "district_rows": district_rows,
            "flash": flash,
            "flash_err": flash_err,
        },
    )


@app.get("/districts/{district_id}", response_class=HTMLResponse, response_model=None)
async def district_detail_page(
    request: Request,
    session: SessionDep,
    district_id: int,
) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    d = await repo.get_district(session, district_id)
    if not d:
        raise HTTPException(404)
    rows = await repo.admin_list_directors_in_district(session, district_id)
    flash, flash_err = _flash_from_query(request)
    return templates.TemplateResponse(
        "district_detail.html",
        {
            "request": request,
            "nav": "districts",
            "district": d,
            "rows": rows,
            "flash": flash,
            "flash_err": flash_err,
        },
    )


@app.get("/districts/new", response_class=HTMLResponse, response_model=None)
async def district_new_form(request: Request) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        "district_form.html",
        {"request": request, "nav": "districts", "district": None, "error": None, "flash": None, "flash_err": None},
    )


@app.post("/districts/new", response_model=None)
async def district_new(
    request: Request,
    session: SessionDep,
    name: str = Form(),
    code: str = Form(default=""),
    sort_order: str = Form(default="0"),
) -> HTMLResponse | RedirectResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    so = _parse_sort_order(sort_order)
    slug = _slugify(code or name)
    try:
        await repo.create_district(session, slug, name, so)
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            "district_form.html",
            {
                "request": request,
                "nav": "districts",
                "district": None,
                "error": "Bu kod allaqachon mavjud. Boshqa kod kiriting.",
                "flash": None,
                "flash_err": None,
            },
            status_code=400,
        )
    return RedirectResponse("/districts?msg=district_added", status_code=302)


@app.get("/districts/{district_id}/edit", response_class=HTMLResponse, response_model=None)
async def district_edit_form(request: Request, session: SessionDep, district_id: int) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    d = await repo.get_district(session, district_id)
    if not d:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "district_form.html",
        {"request": request, "nav": "districts", "district": d, "error": None, "flash": None, "flash_err": None},
    )


@app.post("/districts/{district_id}/edit", response_model=None)
async def district_edit(
    request: Request,
    session: SessionDep,
    district_id: int,
    name: str = Form(),
    code: str = Form(),
    sort_order: str = Form(default="0"),
) -> RedirectResponse | HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    so = _parse_sort_order(sort_order)
    try:
        await repo.update_district(session, district_id, code=_slugify(code), name=name, sort_order=so)
    except IntegrityError:
        await session.rollback()
        d = await repo.get_district(session, district_id)
        return templates.TemplateResponse(
            "district_form.html",
            {
                "request": request,
                "nav": "districts",
                "district": d,
                "error": "Bu kod boshqa tumanda ishlatilgan.",
                "flash": None,
                "flash_err": None,
            },
            status_code=400,
        )
    return RedirectResponse("/districts?msg=district_saved", status_code=302)


@app.post("/districts/{district_id}/delete", response_model=None)
async def district_delete(
    request: Request,
    session: SessionDep,
    district_id: int,
) -> RedirectResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    ok = await repo.delete_district(session, district_id)
    if ok:
        return RedirectResponse("/districts?msg=district_deleted", status_code=302)
    return RedirectResponse("/districts?err=district_has_schools", status_code=302)


@app.get("/directors", response_class=HTMLResponse, response_model=None)
async def directors_table(
    request: Request,
    session: SessionDep,
    q: str = "",
    district_id: int | None = Query(default=None),
    sort: str = Query(default="vote_count"),
    order: str = Query(default="desc"),
    page: int = Query(default=0, ge=0),
) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    per_page = 25
    allowed_sort = {"school_name", "full_name", "district", "sort_order", "vote_count"}
    if sort not in allowed_sort:
        sort = "vote_count"
    order = "asc" if order.lower() == "asc" else "desc"
    page = max(0, page)
    rows, total = await repo.admin_list_directors_page(
        session,
        district_id=district_id,
        search=q,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages - 1:
        page = total_pages - 1
        rows, total = await repo.admin_list_directors_page(
            session,
            district_id=district_id,
            search=q,
            sort=sort,
            order=order,
            page=page,
            per_page=per_page,
        )
    sort_urls = _directors_sort_urls(q, district_id, sort, order)
    page_prev = urlencode(_directors_qs_parts(q, district_id, sort, order, max(0, page - 1)))
    page_next = urlencode(_directors_qs_parts(q, district_id, sort, order, min(total_pages - 1, page + 1)))
    districts = await repo.list_districts(session)
    flash, flash_err = _flash_from_query(request)
    return templates.TemplateResponse(
        "directors.html",
        {
            "request": request,
            "nav": "directors",
            "rows": rows,
            "districts": districts,
            "q": q,
            "district_id": district_id,
            "sort": sort,
            "order": order,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "sort_urls": sort_urls,
            "page_prev_qs": page_prev,
            "page_next_qs": page_next,
            "flash": flash,
            "flash_err": flash_err,
        },
    )


@app.get("/users", response_class=HTMLResponse, response_model=None)
async def users_table(
    request: Request,
    session: SessionDep,
    q: str = "",
    status: str = Query(default="all"),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc"),
    page: int = Query(default=0, ge=0),
    director_id: int | None = Query(default=None),
) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    per_page = 30
    allowed_sort = {"created_at", "telegram_id", "full_name", "username"}
    if sort not in allowed_sort:
        sort = "created_at"
    order = "asc" if order.lower() == "asc" else "desc"
    allowed_status = {"all", "complete", "voted", "no_vote", "incomplete"}
    if status not in allowed_status:
        status = "all"
    page = max(0, page)
    director_choices = await repo.admin_list_directors_for_dropdown(session)
    filter_director = await repo.get_director(session, director_id) if director_id is not None else None
    if director_id is not None and not filter_director:
        director_id = None

    users, total = await repo.admin_list_users_page(
        session,
        search=q,
        status=status,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
        director_id=director_id,
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages - 1:
        page = total_pages - 1
        users, total = await repo.admin_list_users_page(
            session,
            search=q,
            status=status,
            sort=sort,
            order=order,
            page=page,
            per_page=per_page,
            director_id=director_id,
        )
    sort_urls = _users_sort_urls(q, status, sort, order, director_id)
    page_prev = urlencode(_users_qs_parts(q, status, sort, order, max(0, page - 1), director_id))
    page_next = urlencode(_users_qs_parts(q, status, sort, order, min(total_pages - 1, page + 1), director_id))
    flash, flash_err = _flash_from_query(request)
    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "nav": "users",
            "users": users,
            "q": q,
            "status": status,
            "sort": sort,
            "order": order,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "sort_urls": sort_urls,
            "page_prev_qs": page_prev,
            "page_next_qs": page_next,
            "director_id": director_id,
            "director_choices": director_choices,
            "filter_director": filter_director,
            "flash": flash,
            "flash_err": flash_err,
        },
    )


@app.get("/directors/new", response_class=HTMLResponse, response_model=None)
async def director_new_form(request: Request, session: SessionDep) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    districts = await repo.list_districts(session)
    return templates.TemplateResponse(
        "director_form.html",
        {
            "request": request,
            "nav": "directors",
            "director": None,
            "districts": districts,
            "vote_count": 0,
            "error": None,
            "flash": None,
            "flash_err": None,
        },
    )


@app.post("/directors/new", response_model=None)
async def director_new(
    request: Request,
    session: SessionDep,
    district_id: int = Form(),
    full_name: str = Form(),
    school_name: str = Form(),
    sort_order: str = Form(default="0"),
) -> HTMLResponse | RedirectResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    so = _parse_sort_order(sort_order)
    if not full_name.strip() or not school_name.strip():
        districts = await repo.list_districts(session)
        return templates.TemplateResponse(
            "director_form.html",
            {
                "request": request,
                "nav": "directors",
                "director": None,
                "districts": districts,
                "vote_count": 0,
                "error": "Ism-familiya va maktab nomi majburiy.",
                "flash": None,
                "flash_err": None,
            },
            status_code=400,
        )
    await repo.create_director(session, district_id, full_name, school_name, so)
    return RedirectResponse("/directors?msg=director_added", status_code=302)


@app.get("/directors/{director_id}/edit", response_class=HTMLResponse, response_model=None)
async def director_edit_form(request: Request, session: SessionDep, director_id: int) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    d = await repo.get_director(session, director_id)
    if not d:
        raise HTTPException(404)
    districts = await repo.list_districts(session)
    vc = await repo.count_votes_for_director(session, director_id)
    return templates.TemplateResponse(
        "director_form.html",
        {
            "request": request,
            "nav": "directors",
            "director": d,
            "districts": districts,
            "vote_count": vc,
            "error": None,
            "flash": None,
            "flash_err": None,
        },
    )


@app.post("/directors/{director_id}/edit", response_model=None)
async def director_edit(
    request: Request,
    session: SessionDep,
    director_id: int,
    district_id: int = Form(),
    full_name: str = Form(),
    school_name: str = Form(),
    sort_order: str = Form(default="0"),
) -> HTMLResponse | RedirectResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    so = _parse_sort_order(sort_order)
    if not full_name.strip() or not school_name.strip():
        d = await repo.get_director(session, director_id)
        districts = await repo.list_districts(session)
        vc = await repo.count_votes_for_director(session, director_id)
        return templates.TemplateResponse(
            "director_form.html",
            {
                "request": request,
                "nav": "directors",
                "director": d,
                "districts": districts,
                "vote_count": vc,
                "error": "Ism-familiya va maktab nomi majburiy.",
                "flash": None,
                "flash_err": None,
            },
            status_code=400,
        )
    await repo.update_director(
        session,
        director_id,
        district_id=district_id,
        full_name=full_name,
        school_name=school_name,
        sort_order=so,
    )
    return RedirectResponse("/directors?msg=director_saved", status_code=302)


@app.post("/directors/{director_id}/delete", response_model=None)
async def director_delete(request: Request, session: SessionDep, director_id: int) -> RedirectResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    ok = await repo.delete_director(session, director_id)
    if ok:
        return RedirectResponse("/directors?msg=director_deleted", status_code=302)
    return RedirectResponse("/directors?err=director_has_votes", status_code=302)
