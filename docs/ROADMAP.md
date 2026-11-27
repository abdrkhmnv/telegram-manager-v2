# Yo'l xaritasi

Har bir bosqich: mavjud kodni ko'rib chiqish → vazifalar → kod → lint → testlar →
xavfsizlik tahlili → commit → hujjatlar → hisobot.

## 1-bosqich — Foundation ✅

Konfiguratsiya, JSON loglar (maxfiy qiymatlarni yashirish), PostgreSQL async, 18 ta jadval,
Alembic, lease asosidagi vazifa infratuzilmasi, Docker/Compose, CI, zaxira skriptlari.

## 2-bosqich — Telegram yadrosi ✅

Telethon userbot (sessiya 600/700, watchdog, FloodWait), `main.py login`, Control Bot
(aiogram 3), har bir update'da egasi tekshiruvi, bosh menyu, callback himoyasi,
FSM holati PostgreSQL'da, heartbeat va `check --app`.

## 3-bosqich — Chatlar ✅

- [x] Dialoglarni sinxronlash (marked ID, tark etilgan/taqiqlangan chatlar o'tkaziladi)
- [x] Yo'qolgan chatlarni "kira olinmaydi" deb belgilash
- [x] Chatlar/guruhlar/kanallar ro'yxati, sahifalash, saqlanganlar
- [x] Toifalar (yaratish, belgilash, o'chirish), qidiruv

## 4-bosqich — Xabar yuborish ✅

- [x] Qayta ishlatiladigan chat tanlash komponenti (50 tagacha)
- [x] Matn, formatlash, rasm, video, GIF, hujjat, audio, ovozli, albom
- [x] MIME/hajm tekshiruvi, SHA-256 dedup, oldindan ko'rish, tasdiqlash, progress
- [x] Tarix, tahrirlash, o'chirish (tasdiqlash bilan)

## 5-bosqich — Forwarder ✅

- [x] Native va copy rejimlari, albomlar, sarlavha/izoh (copy)
- [x] Kalit so'z va media turi filtrlari, takroriy kontentni aniqlash
- [x] Idempotentlik (`forward_logs`), cheklangan retry, himoyalangan kontentni o'tkazish
- [x] Halqa himoyasi, pauza/davom/o'chirib qo'yish, loglar

## 6-bosqich — Autopost ✅

- [x] Bir martalik, kunlik, haftalik postlar
- [x] Tasodifiy intervalli post: oraliq, faol soatlar, kontent navbati, takrordan himoya
- [x] Lease rejalashtiruvchi: takroriy bajarilish yo'q, faqat xato manzillarga retry,
      restart'dan keyin tiklanish, `task_logs`
- [x] Pauza/davom/bekor qilish/o'chirish, kontentni almashtirish

## 7-bosqich — Media va statistika ✅

- [x] Media menejeri: ro'yxat, ko'rish, yuklash, foydalanilayotganini himoyalab o'chirish
- [x] Statistika faqat bazadagi yozuvlardan: jami, bugun, 7 kun

## 8-bosqich — Mustahkamlash ✅

- [x] Xavfsizlik tahlili (`docs/SECURITY.md` → *8-bosqich tahlili*)
- [x] Servislar uchun integratsion testlar (haqiqiy PostgreSQL + soxta Telethon klienti)
- [x] Panel oqimlari uchun end-to-end testlar (haqiqiy Dispatcher, tarmoqsiz)
- [x] Kichik yuklama testi (3000 chat upsert, 300 vazifani egallash)
- [x] Hujjatlar

## Keyingi qadamlar

- Haqiqiy Telegram akkaunti bilan qo'lda qabul testi va natijalar asosida tuzatishlar.
- Bot API 20 MB cheklovidan katta fayllar uchun boshqa yo'l (masalan, userbot orqali).
- Statistikani CSV eksport qilish.

> Quvvat (nechta chat/xabar) haqidagi raqamlar faqat haqiqiy yuklama testlaridan keyin beriladi.
