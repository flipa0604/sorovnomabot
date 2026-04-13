# Sorovnoma bot (aiogram 3)

500 ta maktab direktori uchun Telegram orqali ovoz berish: kanal obunasi → Instagram havolasi (foydalanuvchi tasdiqlashi) → telefon raqami → inline qidiruv orqali ovoz.

## Talablar

- Python 3.12+ (tavsiya etiladi)
- [BotFather](https://t.me/BotFather) dan olingan `BOT_TOKEN`
- Bot **kanalda administrator** bo‘lishi kerak (obunani `getChatMember` orqali tekshirish uchun)
- `@BotFather` → Bot Settings → **Inline Mode** yoqilgan bo‘lishi kerak (qidiruv uchun)

## O‘rnatish (lokal)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .env ni to‘ldiring
python bot.py
```

PostgreSQL ishlatilsa:

```bash
pip install -r requirements-postgres.txt
```

`.env` da masalan:

```env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sorovnomabot
```

## Direktorlar ro‘yxati (500 ta)

`data/directors_import.csv` faylini UTF-8 bilan to‘ldiring (ustunlar: `full_name`, `region_code`, `region_name`, `school_name`, `sort_order`). Birinchi ishga tushganda jadval bo‘sh bo‘lsa, CSV avtomatik yuklanadi. Keyinroq yangilash uchun ma’lumotlarni qo‘lda import qilish skriptini qo‘shishingiz yoki jadvalni tozalab qayta ishga tushirish mumkin.

## GitHub → Ubuntu server (Docker)

1. Repozitoriyani klonlang:

   ```bash
   git clone https://github.com/SIZNING_USER/sorovnomabot.git
   cd sorovnomabot
   ```

2. Serverda `.env` yarating (`cp .env.example .env` va qiymatlarni kiriting).

3. SQLite bilan:

   ```bash
   docker compose up -d --build
   ```

4. PostgreSQL bilan (`docker-compose.postgres.yml` va `DATABASE_URL` ni moslang):

   ```bash
   pip install -r requirements-postgres.txt   # image ichida Dockerfile ni yangilang yoki
   docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
   ```

   PostgreSQL uchun `Dockerfile` ga `requirements-postgres.txt` o‘rnatish qatorini qo‘shing (yoki image buildda `asyncpg` ni qo‘shing).

## Systemd (Docker siz)

`deploy/sorovnomabot.service` ni ko‘rib chiqing: `WorkingDirectory`, `User`, `EnvironmentFile=/opt/sorovnomabot/.env`.

```bash
sudo cp deploy/sorovnomabot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sorovnomabot
sudo journalctl -u sorovnomabot -f
```

## GitHub Actions

`.github/workflows/docker-build.yml` push vaqtida Docker image build qiladi (push yo‘q, faqat tekshiruv).

## Admin

`.env` da `ADMIN_IDS` — Telegram user ID (vergul bilan). Buyruqlar:

- `/admin` — yordam
- `/stats` — jami ovoz va TOP
- `/export` — Excel (pandas/openpyxl)

## Eslatmalar

- **Instagram**: Telegram API Instagramga kirishni tekshira olmaydi; havola + «Ko‘rdim» tugmasi bilan tasdiqlanadi.
- **FSM**: hozircha `MemoryStorage` — bot qayta ishga tushganda sessiya yo‘qoladi. Yuqori yuk uchun `RedisStorage` ga o‘tkazing.
- **Xavfsizlik**: token va `.env` ni hech qachon gitga qo‘shmang; kanalda bot huquqlarini minimal qoldiring.
