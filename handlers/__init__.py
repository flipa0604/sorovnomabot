from aiogram import Router

from handlers.admin import router as admin_router
from handlers.registration import router as registration_router
from handlers.voting import router as voting_router


def setup_routers() -> Router:
    root = Router()
    root.include_router(admin_router)
    root.include_router(registration_router)
    root.include_router(voting_router)
    return root
