# O'rnatish va ishga tushirish

Uch xil usul: **VPS + Docker Compose** (tavsiya), **VPS + systemd** (Docker'siz) va
**Termux** (Android, ishlab chiqish va sinov uchun).

## 1. VPS + Docker Compose (tavsiya etiladi)

Talablar: Docker Engine va Docker Compose v2 plagini.

```bash
sudo mkdir -p /opt/telegram-manager-v2 && sudo chown "$USER" /opt/telegram-manager-v2
git clone https://github.com/abdrkhmnv/telegram-manager-v2.git /opt/telegram-manager-v2
cd /opt/telegram-manager-v2
cp .env.example .env && chmod 600 .env
nano .env        # POSTGRES_PASSWORD, APP_ENV=production, TELEGRAM_*, BOT_TOKEN, OWNER_TELEGRAM_ID
docker compose up -d --build db migrate
docker compose run --rm app python main.py login     # bir martalik, interaktiv
docker compose up -d --build
```

Tekshirish:

```bash
docker compose ps                         # db: healthy, migrate: exited (0), app: healthy
docker compose exec app python main.py check
docker compose logs -f app
```

- Xizmatlar ketma-ketligi: `db` (healthcheck) → `migrate` (`alembic upgrade head`) → `app`.
- `DATABASE_URL` konteyner ichida avtomatik `db` xostiga yo'naltiriladi —
  `POSTGRES_USER/PASSWORD/DB` dan quriladi.
- PostgreSQL porti tashqariga ochilmaydi.
- Ma'lumotlar `pgdata`, `app_storage`, `app_logs` volume'larida saqlanadi.

Yangilash:

```bash
cd /opt/telegram-manager-v2
scripts/backup_db.sh --docker            # avval zaxira
git pull
docker compose up -d --build             # migrate xizmati yangi migratsiyalarni qo'llaydi
```

To'xtatish: `docker compose stop` (ma'lumotlar saqlanadi). `docker compose down -v`
**volume'larni ham o'chiradi** — faqat hammasini yo'q qilmoqchi bo'lsangiz ishlating.

## 2. VPS + systemd (Docker'siz)

```bash
sudo apt install -y python3 python3-venv postgresql
sudo -u postgres psql -c "CREATE USER tgmanager WITH PASSWORD 'KUCHLI_PAROL';"
sudo -u postgres psql -c "CREATE DATABASE tgmanager OWNER tgmanager;"

sudo useradd --system --home /opt/telegram-manager-v2 --shell /usr/sbin/nologin tgmanager
sudo git clone https://github.com/abdrkhmnv/telegram-manager-v2.git /opt/telegram-manager-v2
cd /opt/telegram-manager-v2
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp .env.example .env    # DATABASE_URL va boshqalarni to'ldiring
sudo chown -R tgmanager:tgmanager /opt/telegram-manager-v2
sudo chmod 600 .env
sudo -u tgmanager .venv/bin/alembic upgrade head
sudo -u tgmanager .venv/bin/python main.py check
sudo -u tgmanager .venv/bin/python main.py login     # bir martalik, interaktiv
```

`/etc/systemd/system/telegram-manager.service`:

```ini
[Unit]
Description=Telegram Manager v2
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=tgmanager
WorkingDirectory=/opt/telegram-manager-v2
ExecStartPre=/opt/telegram-manager-v2/.venv/bin/alembic upgrade head
ExecStart=/opt/telegram-manager-v2/.venv/bin/python main.py run
Restart=on-failure
RestartSec=10
TimeoutStopSec=45
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/telegram-manager-v2/storage /opt/telegram-manager-v2/logs

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-manager
journalctl -u telegram-manager -f
```

## 3. Termux (Android)

Termux'da Docker kerak emas. PostgreSQL to'g'ridan-to'g'ri Termux ichida ishlaydi.

```bash
pkg update && pkg upgrade
pkg install -y python git postgresql clang make
# asyncpg C kengaytmasini yig'ish uchun clang/make kerak bo'lishi mumkin

initdb "$PREFIX/var/lib/postgresql"
pg_ctl -D "$PREFIX/var/lib/postgresql" -l "$PREFIX/var/lib/postgresql/server.log" start
createuser tgmanager
createdb -O tgmanager tgmanager
psql -d tgmanager -c "ALTER USER tgmanager WITH PASSWORD 'KUCHLI_PAROL';"

git clone https://github.com/abdrkhmnv/telegram-manager-v2.git
cd telegram-manager-v2
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && chmod 600 .env
# .env: DATABASE_URL=postgresql+asyncpg://tgmanager:KUCHLI_PAROL@localhost:5432/tgmanager
alembic upgrade head
python main.py check
python main.py login     # bir martalik
python main.py run
```

Maslahatlar:

- Telefon uxlaganda jarayon to'xtamasligi uchun: `termux-wake-lock`.
- Termux qayta ochilganda PostgreSQL'ni qayta ishga tushiring:
  `pg_ctl -D "$PREFIX/var/lib/postgresql" start`.
- Termux mobil qurilma — uzoq muddatli ishlab chiqarish uchun VPS ishonchliroq.
- Termux'dagi paketlar versiyalari tez-tez o'zgaradi; `pip install` xato bersa,
  avval `pkg upgrade`, keyin xato matnidagi yetishmayotgan paketni o'rnating.

## Healthcheck

`python main.py check` — konfiguratsiyani yuklaydi, PostgreSQL'ga ulanadi va sxema
oxirgi migratsiyada ekanini tekshiradi. `0` = sog'lom, `1` = baza/migratsiya muammosi,
`2` = konfiguratsiya xatosi.

`python main.py check --app` — qo'shimcha ravishda ishlayotgan ilovaning heartbeat
faylini (`storage/health.json`, har 30 soniyada yangilanadi) tekshiradi: userbot ulangan
va Control Bot polling ishlayotgan bo'lishi kerak, fayl 2 daqiqadan eski bo'lmasligi kerak.
Docker `HEALTHCHECK` shu buyruqdan foydalanadi. Healthcheck alohida jarayon bo'lgani uchun
Telethon sessiyasini ochmaydi.

## Loglar

- Konsol (Docker: `docker compose logs app`, systemd: `journalctl`).
- Fayl: `logs/app.log` (10 MB × 5 aylanma). `LOG_DIR=` bo'sh qoldirilsa fayl yozilmaydi.
- Format: `LOG_FORMAT=json` (mashina uchun) yoki `text` (o'qish uchun).
