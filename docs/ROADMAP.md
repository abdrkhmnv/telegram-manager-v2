# Yo'l xaritasi

Har bir bosqich: mavjud kodni ko'rib chiqish → vazifalar → kod → lint → testlar →
xavfsizlik tahlili → commit → hujjatlar → hisobot. Avval kichik, to'liq ishlaydigan qism.

## 1-bosqich — Foundation ✅

- [x] Loyiha tuzilmasi, `pyproject.toml`, qat'iy versiyalar
- [x] Konfiguratsiya (Pydantic Settings, 3 guruh, maxfiy qiymatlar `SecretStr`)
- [x] Tuzilmali JSON loglar, maxfiy qiymatlarni yashirish, fayl rotatsiyasi
- [x] PostgreSQL async ulanish, pul, timeout'lar, backoff bilan kutish
- [x] 18 ta jadval: modellar, `0001` migratsiyasi, nomlash konvensiyasi
- [x] Repozitoriylar: sozlamalar, chatlar, forward loglari, autopost (lease), occurrence, audit
- [x] Vaqt hisoblari (Asia/Tashkent, kunlik/haftalik/tasodifiy, faol soatlar)
- [x] Lifecycle menejeri, `main.py run|check`, startup'da migratsiya tekshiruvi
- [x] Docker, Docker Compose (db → migrate → app), healthcheck
- [x] GitHub Actions: ruff, mypy, alembic up/down/check, pytest (3.11–3.13), docker build
- [x] Zaxira/tiklash skriptlari, o'zbekcha hujjatlar

## 2-bosqich — Telegram yadrosi

- [ ] Telethon klienti: sessiya (`700`), qayta ulanish (eksponensial backoff), FloodWait
- [ ] Birinchi kirish oqimi (telefon, kod, 2FA) — kodlar log'ga yozilmaydi
- [ ] Control Bot (aiogram 3), `OWNER_TELEGRAM_ID` middleware — har bir update'da
- [ ] `/start`, `/help`, bosh menyu (12 bo'lim), orqaga/bosh sahifa navigatsiyasi
- [ ] Callback ma'lumotlari: 64 bayt chegarasi, eskirgan callback'larni xavfsiz qayta ishlash
- [ ] Takroriy callback'dan himoya, xavfli amallar uchun tasdiqlash
- [ ] Healthcheck'ga Telegram ulanish holati
- [ ] `docs/USER_GUIDE.md` — panel bo'yicha qo'llanma

## 3-bosqich — Chatlar

- [ ] Dialoglarni sinxronlash (`ChatRepository.upsert_many`), kira olinmaydiganlarni belgilash
- [ ] Toifalar, qidiruv, sahifalash, saqlangan chatlar

## 4-bosqich — Xabar yuborish

- [ ] Matn/formatlangan matn, rasm, video, hujjat, audio, ovozli xabar
- [ ] Bir nechta manzil, oldindan ko'rish, tasdiqlash, tahrirlash/o'chirish, tarix

## 5-bosqich — Forwarder

- [ ] Native va copy rejimlari, albomlar, filtrlar (kalit so'z, media turi)
- [ ] Idempotentlik (`forward_logs`), takroriy kontentni aniqlash, cheklangan retry
- [ ] Himoyalangan/kira olinmaydigan manbalarni o'tkazib yuborish

## 6-bosqich — Autopost

- [ ] Rejalashtirilgan (bir martalik, kunlik, haftalik) va tasodifiy interval
- [ ] Lease asosidagi rejalashtiruvchi, restart'dan keyin tiklanish, `task_logs`

## 7-bosqich — Media va statistika

- [ ] Media menejeri (MIME/hajm tekshiruvi, SHA-256 dedup, vaqtinchalik fayllarni tozalash)
- [ ] Statistika — faqat bazadagi haqiqiy yozuvlardan (kunlik/haftalik)

## 8-bosqich — Mustahkamlash

- [ ] Xavfsizlik tahlili, integratsion va yuklama testlari, deploy tekshiruvi

> Quvvat (nechta chat/xabar) haqidagi raqamlar faqat yuklama testlaridan keyin beriladi.
