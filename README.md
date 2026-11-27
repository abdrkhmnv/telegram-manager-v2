# Telegram Manager v2

Bitta shaxsiy Telegram akkauntini alohida **Control Bot** orqali boshqarish tizimi.
Haqiqiy amallarni (yuborish, forward, autopost) akkaunt Telethon (MTProto) orqali bajaradi,
Control Bot esa faqat boshqaruv paneli vazifasini o'taydi. Panelga faqat
`OWNER_TELEGRAM_ID` da ko'rsatilgan egasi kira oladi. Barcha interfeys o'zbek tilida (lotin).

> **Holat:** 1-bosqich (Foundation) tayyor — konfiguratsiya, loglash, PostgreSQL,
> modellar, migratsiyalar, vazifalarni atomik egallash infratuzilmasi, Docker va CI.
> Telegram qismi (userbot va Control Bot) 2-bosqichda qo'shiladi.
> To'liq reja: [docs/ROADMAP.md](docs/ROADMAP.md).

## Imkoniyatlar

| Imkoniyat | Holat |
|---|---|
| Pydantic Settings konfiguratsiyasi, maxfiy qiymatlarni tekshirish | ✅ tayyor |
| Tuzilmali JSON loglar, tokenlar/parollarni avtomatik yashirish | ✅ tayyor |
| PostgreSQL (SQLAlchemy 2 async + asyncpg), ulanishni qayta urinish | ✅ tayyor |
| 18 ta jadval, Alembic migratsiyasi, startup'da sxema tekshiruvi | ✅ tayyor |
| Vazifalarni atomik egallash (`FOR UPDATE SKIP LOCKED` + lease) | ✅ tayyor |
| Idempotent forward/post yozuvlari (takroriy yuborishdan himoya) | ✅ tayyor |
| Asia/Tashkent vaqt hisoblari (kunlik, haftalik, tasodifiy interval) | ✅ tayyor |
| Docker, Docker Compose, GitHub Actions CI | ✅ tayyor |
| Telethon userbot, Control Bot, egasi avtorizatsiyasi, bosh menyu | ⏳ 2-bosqich |
| Chatlar, xabar yuborish, forwarder, autopost, media, statistika | ⏳ 3–7-bosqichlar |

## Arxitektura (qisqacha)

```
main.py            -> buyruqlar: run | check
app/               -> config, bootstrap, lifecycle (komponentlarni boshqarish)
core/              -> ilova istisnolari (2-bosqichdan: userbot, control_bot)
database/          -> base, models, repositories, migrations, connection
utils/             -> logger, time_utils, validators, helpers
tests/unit         -> bazasiz testlar
tests/integration  -> haqiqiy PostgreSQL testlari
```

Batafsil: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Baza: [docs/DATABASE.md](docs/DATABASE.md)

## Talablar

- Python **3.11+** (CI 3.11, 3.12, 3.13 da tekshiradi)
- PostgreSQL **14+** (CI va Docker: 16)
- Docker + Docker Compose v2 — ixtiyoriy (VPS uchun tavsiya etiladi; Termux'da shart emas)

## Tez boshlash (Docker Compose)

```bash
git clone https://github.com/abdrkhmnv/telegram-manager-v2.git
cd telegram-manager-v2
cp .env.example .env && chmod 600 .env
# .env ichida kamida POSTGRES_PASSWORD ni almashtiring (CHANGE_ME qolmasin)
docker compose up -d --build
docker compose ps                       # app "healthy" bo'lishi kerak
docker compose exec app python main.py check
```

`migrate` xizmati `alembic upgrade head` ni avtomatik bajaradi, keyin `app` ishga tushadi.

## Mahalliy o'rnatish (Docker'siz)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env && chmod 600 .env   # DATABASE_URL ni to'ldiring
alembic upgrade head                     # jadvallarni yaratish
python main.py check                     # PostgreSQL: OK / Migratsiyalar: OK
python main.py run                       # Ctrl+C bilan to'xtatiladi
```

Termux va VPS bo'yicha batafsil qo'llanma: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Muhit o'zgaruvchilari

| O'zgaruvchi | Majburiy | Standart | Izoh |
|---|---|---|---|
| `DATABASE_URL` | ha | — | `postgresql+asyncpg://user:parol@host:5432/baza` |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | yo'q | 5, 5 | Ulanishlar puli |
| `DB_CONNECT_TIMEOUT`, `DB_COMMAND_TIMEOUT` | yo'q | 10, 30 | Soniyalarda |
| `APP_ENV` | yo'q | `development` | `development` \| `production` |
| `LOG_LEVEL` / `LOG_FORMAT` | yo'q | `INFO` / `json` | `json` \| `text` |
| `LOG_DIR` | yo'q | `logs` | Bo'sh = faqat konsol |
| `TIMEZONE` | yo'q | `Asia/Tashkent` | Interfeys vaqt zonasi (bazada doim UTC) |
| `STORAGE_DIR` | yo'q | `storage` | Media va sessiyalar katalogi |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | 2-bosqichdan | — | https://my.telegram.org |
| `BOT_TOKEN` | 2-bosqichdan | — | @BotFather |
| `OWNER_TELEGRAM_ID` | 2-bosqichdan | — | Panel egasining raqamli ID'si |
| `SESSION_DIR`, `SESSION_NAME` | yo'q | `storage/sessions`, `userbot` | Telethon sessiyasi |

Konfiguratsiya xatosida ilova `2` kodi bilan chiqadi va qaysi maydon noto'g'ri ekanini
yozadi — qiymatning o'zini (parol, token) hech qachon chiqarmaydi.

## Telegram API sozlash (2-bosqich uchun tayyorgarlik)

1. https://my.telegram.org → *API development tools* → ilova yarating →
   `api_id` va `api_hash` ni `.env` ga yozing.
2. @BotFather → `/newbot` → tokenni `BOT_TOKEN` ga yozing.
3. O'z ID raqamingizni bilish uchun @userinfobot ga yozing → `OWNER_TELEGRAM_ID`.

Birinchi kirish (telefon raqami va kod bilan Telethon sessiyasini yaratish) 2-bosqichda
qo'shiladi va shu yerda hujjatlashtiriladi.

## Testlar va sifat tekshiruvi

```bash
ruff check . && ruff format --check .
mypy
pytest tests/unit                                  # bazasiz
export TEST_DATABASE_URL=postgresql+asyncpg://user:parol@localhost:5432/tgmanager_test
DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
pytest                                             # unit + integration
DATABASE_URL=$TEST_DATABASE_URL alembic check      # modellar == migratsiyalar
```

> `TEST_DATABASE_URL` uchun **alohida** test bazasidan foydalaning: integratsion testlar
> har bir testdan oldin barcha jadvallarni tozalaydi.

## Muammolarni hal qilish

| Belgi | Sabab va yechim |
|---|---|
| `Konfiguratsiya xatosi ... DATABASE_URL` | `.env` yo'q yoki URL `postgresql+asyncpg://` bilan boshlanmaydi |
| `PostgreSQL'ga ulanib bo'lmadi` | Server ishlamayapti, host/port noto'g'ri yoki parol xato. `pg_isready` bilan tekshiring |
| `Migratsiyalar: ESKIRGAN` | `alembic upgrade head` bajaring |
| `app` konteyneri `unhealthy` | `docker compose logs app migrate` — odatda migratsiya yoki parol muammosi |
| Termux'da `asyncpg` o'rnatilmaydi | `pkg install clang make` va qayta urining (DEPLOYMENT.md) |

## Xavfsizlik

- `.env`, `*.session`, `storage/`, `logs/`, `backups/` Git'ga **hech qachon** tushmaydi (`.gitignore`).
- `.env` va sessiya katalogi ruxsatlari: `chmod 600 .env`, `chmod 700 storage/sessions`.
- Loglarda bot tokenlari, URL parollari va ro'yxatga olingan maxfiy qiymatlar `***` bilan almashtiriladi.
- Tizim Telegram cheklovlari, anti-spam mexanizmlari va himoyalangan kontentni chetlab o'tmaydi
  va notanish odamlarga avtomatik xabar yubormaydi.
- Ma'lumotlar sizib chiqsa nima qilish kerak: [docs/SECURITY.md](docs/SECURITY.md).

## Hujjatlar

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — tuzilma va dizayn qarorlari
- [DATABASE.md](docs/DATABASE.md) — jadvallar, migratsiyalar, zaxira nusxa
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — VPS (Docker / systemd) va Termux
- [USER_GUIDE.md](docs/USER_GUIDE.md) — foydalanish qo'llanmasi
- [SECURITY.md](docs/SECURITY.md) — xavfsizlik va kalitlarni almashtirish
- [ROADMAP.md](docs/ROADMAP.md) — bosqichlar va holat
