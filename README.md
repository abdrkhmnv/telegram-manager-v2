# Telegram Manager v2

Bitta shaxsiy Telegram akkauntini alohida **Control Bot** orqali boshqarish tizimi.
Haqiqiy amallarni (yuborish, forward, autopost) akkaunt Telethon (MTProto) orqali bajaradi,
Control Bot esa faqat boshqaruv paneli vazifasini o'taydi. Panelga faqat
`OWNER_TELEGRAM_ID` da ko'rsatilgan egasi kira oladi. Barcha interfeys o'zbek tilida (lotin).

> **Holat:** 1–8-bosqichlarning barchasi tayyor va CI'da sinovdan o'tgan. Haqiqiy Telegram
> kalitlari bilan qo'lda qabul testi hali o'tkazilmagan. Reja: [docs/ROADMAP.md](docs/ROADMAP.md).

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
| Telethon userbot: sessiya (600/700), qayta ulanish, FloodWait | ✅ tayyor |
| Control Bot: egasi tekshiruvi, bosh menyu, /start, /help, tizim holati | ✅ tayyor |
| Takroriy tugma bosishdan himoya, eskirgan tugmalarni xavfsiz qayta ishlash | ✅ tayyor |
| Bot holatini (FSM) PostgreSQL'da saqlash | ✅ tayyor |
| Chatlar: sinxronlash, toifalar, qidiruv, sahifalash | ✅ tayyor |
| Xabar yuborish: matn/media/albom, oldindan ko'rish, tasdiqlash, tarix, tahrir/o'chirish | ✅ tayyor |
| Forwarder: native va copy, filtrlar, takrorni aniqlash, idempotentlik, retry | ✅ tayyor |
| Autopost: bir martalik/kunlik/haftalik va tasodifiy interval (faol soatlar, navbat) | ✅ tayyor |
| Media Manager va bazaga asoslangan statistika | ✅ tayyor |

## Arxitektura (qisqacha)

```
main.py            -> buyruqlar: run | login | check [--app]
app/               -> config, bootstrap, lifecycle, permissions, health
core/              -> userbot (Telethon), control_bot (aiogram), login, FloodWait
bot/               -> panel: callbacks, klaviaturalar, ekranlar, handlerlar, middleware, picker
services/          -> chatlar, xabarlar, media, forwarder, autopost, rejalashtiruvchi, statistika
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
# .env ichida Telegram kalitlarini ham to'ldiring (pastdagi bo'limga qarang)
docker compose up -d db migrate                       # baza va migratsiya
docker compose run --rm app python main.py login      # BIR MARTA: Telegram'ga kirish
docker compose up -d --build                          # ilovani ishga tushirish
docker compose ps                                     # app "healthy" bo'lishi kerak
```

So'ng Telegram'da botingizga `/start` yozing — bosh menyu ochiladi.

## Mahalliy o'rnatish (Docker'siz)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env && chmod 600 .env   # DATABASE_URL ni to'ldiring
alembic upgrade head                     # jadvallarni yaratish
python main.py check                     # PostgreSQL: OK / Migratsiyalar: OK
python main.py login                     # BIR MARTA: telefon, kod, 2FA
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
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | `run`/`login` uchun | — | https://my.telegram.org |
| `BOT_TOKEN` | `run` uchun | — | @BotFather |
| `OWNER_TELEGRAM_ID` | `run` uchun | — | Panel egasining raqamli ID'si |
| `SESSION_DIR`, `SESSION_NAME` | yo'q | `storage/sessions`, `userbot` | Telethon sessiyasi |

Konfiguratsiya xatosida ilova `2` kodi bilan chiqadi va qaysi maydon noto'g'ri ekanini
yozadi — qiymatning o'zini (parol, token) hech qachon chiqarmaydi.

## Telegram API sozlash

1. https://my.telegram.org → *API development tools* → ilova yarating →
   `api_id` va `api_hash` ni `.env` ga yozing.
2. @BotFather → `/newbot` → tokenni `BOT_TOKEN` ga yozing.
3. O'z ID raqamingizni bilish uchun @userinfobot ga yozing → `OWNER_TELEGRAM_ID`.
4. Yangi botingizga Telegram'da bir marta `/start` yozing (bot sizga javob bera olishi uchun).

## Birinchi kirish

```bash
python main.py login
# Telefon raqam (+998...): ...
# Telegram yuborgan kod: ...
# Ikki bosqichli tekshiruv paroli: ...   (yoqilgan bo'lsa; ekranda ko'rinmaydi)
```

Sessiya `storage/sessions/userbot.session` ga `600` ruxsat bilan saqlanadi. Telefon, kod
va parol hech qayerga yozilmaydi. Bu bir martalik amal — keyin `python main.py run` terminal
savollarisiz ishlaydi. Sessiya bekor qilinsa, ilova ishga tushmaydi va `login` ni qayta
bajarishni so'raydi.

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
| `Telegram akkaunti ulanmagan` | `python main.py login` (Docker: `docker compose run --rm app python main.py login`) |
| `BOT_TOKEN noto'g'ri` | @BotFather'dan tokenni tekshiring yoki yangisini oling |
| Bot javob bermayapti | `OWNER_TELEGRAM_ID` to'g'rimi? Bot faqat egasiga va faqat shaxsiy chatda javob beradi |
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
