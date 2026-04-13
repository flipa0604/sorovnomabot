import re


def normalize_phone(raw: str) -> str:
    """O'zbekiston raqami: faqat raqamlar, 998XXXXXXXXX (12 ta)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) >= 12 and digits.startswith("998"):
        return digits[:12]
    if len(digits) == 9:
        return "998" + digits
    if len(digits) == 12:
        return digits
    return digits
