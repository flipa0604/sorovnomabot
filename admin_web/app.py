from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request
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


@app.get("/login", response_class=HTMLResponse)
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


@app.post("/login")
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


@app.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: SessionDep) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    rows = await repo.directors_with_vote_counts(session)
    districts = await repo.list_districts(session)
    total_votes = sum(c for _, c in rows)
    msg = request.query_params.get("msg")
    err = request.query_params.get("err")
    flash = None
    flash_err = None
    if msg == "district_added":
        flash = "Tuman qo'shildi."
    elif msg == "district_saved":
        flash = "Tuman saqlandi."
    elif msg == "district_deleted":
        flash = "Tuman o'chirildi."
    elif msg == "director_added":
        flash = "Direktor / maktab qo'shildi."
    elif msg == "director_saved":
        flash = "Ma'lumotlar saqlandi."
    elif msg == "director_deleted":
        flash = "Qator o'chirildi."
    if err == "district_has_schools":
        flash_err = "Tumanda maktablar bor — avval ularni o'chiring yoki ko'chiring."
    elif err == "director_has_votes":
        flash_err = "Ovoz yig'gan direktorni o'chirib bo'lmaydi."
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rows": rows,
            "districts": districts,
            "total_votes": total_votes,
            "flash": flash,
            "flash_err": flash_err,
        },
    )


@app.get("/districts/new", response_class=HTMLResponse)
async def district_new_form(request: Request) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("district_form.html", {"request": request, "district": None, "error": None})


@app.post("/districts/new")
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
                "district": None,
                "error": "Bu kod allaqachon mavjud. Boshqa kod kiriting.",
            },
            status_code=400,
        )
    return RedirectResponse("/?msg=district_added", status_code=302)


@app.get("/districts/{district_id}/edit", response_class=HTMLResponse)
async def district_edit_form(request: Request, session: SessionDep, district_id: int) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    d = await repo.get_district(session, district_id)
    if not d:
        raise HTTPException(404)
    return templates.TemplateResponse(
        "district_form.html",
        {"request": request, "district": d, "error": None},
    )


@app.post("/districts/{district_id}/edit")
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
                "district": d,
                "error": "Bu kod boshqa tumanda ishlatilgan.",
            },
            status_code=400,
        )
    return RedirectResponse("/?msg=district_saved", status_code=302)


@app.post("/districts/{district_id}/delete")
async def district_delete(
    request: Request,
    session: SessionDep,
    district_id: int,
) -> RedirectResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    ok = await repo.delete_district(session, district_id)
    if ok:
        return RedirectResponse("/?msg=district_deleted", status_code=302)
    return RedirectResponse("/?err=district_has_schools", status_code=302)


@app.get("/directors/new", response_class=HTMLResponse)
async def director_new_form(request: Request, session: SessionDep) -> HTMLResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    districts = await repo.list_districts(session)
    return templates.TemplateResponse(
        "director_form.html",
        {
            "request": request,
            "director": None,
            "districts": districts,
            "vote_count": 0,
            "error": None,
        },
    )


@app.post("/directors/new")
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
                "director": None,
                "districts": districts,
                "vote_count": 0,
                "error": "Ism-familiya va maktab nomi majburiy.",
            },
            status_code=400,
        )
    await repo.create_director(session, district_id, full_name, school_name, so)
    return RedirectResponse("/?msg=director_added", status_code=302)


@app.get("/directors/{director_id}/edit", response_class=HTMLResponse)
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
        {"request": request, "director": d, "districts": districts, "vote_count": vc, "error": None},
    )


@app.post("/directors/{director_id}/edit")
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
                "director": d,
                "districts": districts,
                "vote_count": vc,
                "error": "Ism-familiya va maktab nomi majburiy.",
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
    return RedirectResponse("/?msg=director_saved", status_code=302)


@app.post("/directors/{director_id}/delete")
async def director_delete(request: Request, session: SessionDep, director_id: int) -> RedirectResponse:
    if not _admin_session_ok(request):
        return RedirectResponse("/login", status_code=302)
    ok = await repo.delete_director(session, director_id)
    if ok:
        return RedirectResponse("/?msg=director_deleted", status_code=302)
    return RedirectResponse("/?err=director_has_votes", status_code=302)
