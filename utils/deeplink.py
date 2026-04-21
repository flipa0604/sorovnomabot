"""Bot /start parametri: d{school_id} (Telegram start payload qoidalari; maktab yozuvi id)."""

import re

_SCHOOL_START = re.compile(r"^d(\d+)$", re.IGNORECASE)


def school_start_payload(school_id: int) -> str:
    return f"d{school_id}"


def parse_school_start_payload(args: str | None) -> int | None:
    if not args:
        return None
    m = _SCHOOL_START.match(args.strip())
    if not m:
        return None
    return int(m.group(1))
