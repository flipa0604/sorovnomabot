"""Web-admin serverini ishga tushirish: python run_admin_web.py"""

import logging
import sys

import uvicorn

from config import get_settings

logging.basicConfig(level=logging.INFO)


def main() -> None:
    s = get_settings()
    if not (s.web_admin_password or "").strip():
        print("Xatolik: .env faylida WEB_ADMIN_PASSWORD belgilang.", file=sys.stderr)
        sys.exit(1)
    uvicorn.run(
        "admin_web.app:app",
        host=s.web_admin_host,
        port=s.web_admin_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
