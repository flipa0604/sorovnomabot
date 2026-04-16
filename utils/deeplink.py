"""Bot /start parametri: d{director_id} (Telegram start payload qoidalari)."""

import re

_DIRECTOR_START = re.compile(r"^d(\d+)$", re.IGNORECASE)


def director_start_payload(director_id: int) -> str:
    return f"d{director_id}"


def parse_director_start_payload(args: str | None) -> int | None:
    if not args:
        return None
    m = _DIRECTOR_START.match(args.strip())
    if not m:
        return None
    return int(m.group(1))
