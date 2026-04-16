"""Telegram Web App initData tekshiruvi (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

# Mini App ochilganda initData yuboriladi, sessiya ochiladi va bosh sahifaga yo'naltiriladi.
TG_APP_BRIDGE_HTML = """<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>Admin</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; background: #0a0e14; color: #e7ecf3; margin: 0; padding: 1.5rem; text-align: center; }
    p { margin: 0.5rem 0; color: #8b98a8; font-size: 0.95rem; }
  </style>
</head>
<body>
  <p id="msg">Kirish tekshirilmoqda…</p>
  <script>
    (function () {
      var tg = window.Telegram && window.Telegram.WebApp;
      if (!tg) {
        document.getElementById("msg").textContent =
          "Bu sahifani Telegram ichidagi Web App tugmasi orqali oching.";
        return;
      }
      tg.ready();
      tg.expand();
      var initData = tg.initData || "";
      if (!initData) {
        document.getElementById("msg").textContent =
          "initData yo'q. Telegram mobil ilovasidan Web App orqali kiriting.";
        return;
      }
      fetch("/auth/tg-webapp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: initData }),
        credentials: "same-origin",
      })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (x) {
          if (x.ok && x.j && x.j.ok) {
            window.location.href = x.j.redirect || "/";
            return;
          }
          var err = (x.j && x.j.error) || "Kirish rad etildi.";
          document.getElementById("msg").textContent = err;
          if (tg.showAlert) tg.showAlert(err);
        })
        .catch(function () {
          document.getElementById("msg").textContent = "Tarmoq xatosi.";
        });
    })();
  </script>
</body>
</html>"""


def parse_webapp_init_data_user_id(
    init_data: str,
    bot_token: str,
    *,
    max_age_sec: int = 86400,
) -> int | None:
    """initData dan foydalanuvchi Telegram ID; noto'g'ri yoki eskirgan bo'lsa None."""
    if not (init_data and init_data.strip() and bot_token):
        return None
    try:
        vals = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    except Exception:
        return None
    received_hash = vals.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(vals.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    try:
        auth_date = int(vals.get("auth_date") or 0)
    except ValueError:
        auth_date = 0
    if auth_date and (time.time() - auth_date) > max_age_sec:
        return None
    raw_user = vals.get("user")
    if not raw_user:
        return None
    try:
        user = json.loads(raw_user)
        return int(user["id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None
