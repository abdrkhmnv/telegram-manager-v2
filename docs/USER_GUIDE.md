# Foydalanish qo'llanmasi

## Boshlash

1. `.env` ni to'ldiring (README → *Telegram API sozlash*).
2. Telegram'da botingizga bir marta `/start` yozing.
3. Serverda bir marta: `python main.py login` (Docker:
   `docker compose run --rm app python main.py login`).
4. Ilovani ishga tushiring: `python main.py run` (Docker: `docker compose up -d`).
5. Botga `/start` yozing — bosh menyu ochiladi.

Bot **faqat** `OWNER_TELEGRAM_ID` egasiga va faqat bot bilan shaxsiy chatda javob beradi.
Boshqa odamlar yozsa, bot umuman javob bermaydi.

## Buyruqlar

| Buyruq | Nima qiladi |
|---|---|
| `/start` | Bosh menyuni ochadi |
| `/help` | Qisqa yordam |

Boshqa matn yuborilsa, bot `/start` ni bosishni eslatadi.

## Bosh menyu

| Tugma | Holat | Bo'lim |
|---|---|---|
| 📤 Xabar yuborish | 4-bosqich | Bir yoki bir nechta chatga matn/media yuborish, oldindan ko'rish |
| 🔁 Forwarder | 5-bosqich | Native va copy rejimidagi forward qoidalari |
| 📅 Autopost | 6-bosqich | Bir martalik, kunlik, haftalik postlar |
| 🎲 Random Autopost | 6-bosqich | Belgilangan oraliqda tasodifiy vaqtda navbatdan post |
| 🖼 Media Manager | 7-bosqich | Saqlangan media fayllar |
| 💬 Chatlar · 👥 Guruhlar · 📢 Kanallar | 3-bosqich | Dialoglar ro'yxati, qidiruv, toifalar |
| 🔎 Qidiruv | 3-bosqich | Chatlarni nom yoki username bo'yicha topish |
| 📊 Statistika | 7-bosqich | Bazadagi haqiqiy yozuvlar asosidagi hisobotlar |
| ⚙️ Sozlamalar | ✅ ishlaydi | Tizim holati (quyida) |
| ❓ Yordam | ✅ ishlaydi | Qisqa yo'riqnoma |

Hali tayyor bo'lmagan bo'lim bosilsa, bot u qaysi bosqichda qo'shilishini aytadi.

## Navigatsiya

- **⬅️ Orqaga** — oldingi bo'limga, **🏠 Bosh menyu** — bosh menyuga.
- Bot yangi xabar yubormasdan, mavjud panel xabarini o'zgartiradi — chat to'lib ketmaydi.
- Tugmani tez-tez ikki marta bossangiz, ikkinchisi e'tiborsiz qoldiriladi. Oldingi amal
  tugamagan bo'lsa, "⏳ Oldingi amal bajarilmoqda" degan javob keladi.
- Eski xabardagi tugma ishlamay qolsa ("Bu tugma eskirgan"), bot bosh menyuni qayta ochadi.

## ⚙️ Sozlamalar → ℹ️ Tizim holati

| Qator | Ma'nosi |
|---|---|
| ✅/❌ Userbot | Telegram akkaunti ulanganmi; ism, username va ID |
| ✅/❌ PostgreSQL | Bazaga ulanish |
| ✅/❌ Migratsiya | Baza sxemasi oxirgi versiyadami |
| Versiya, Ishlamoqda | Ilova versiyasi va qancha vaqtdan beri ishlayapti |
| Tekshirildi | Oxirgi tekshiruv vaqti (Asia/Tashkent) |

**🔄 Yangilash** holatni qayta tekshiradi.

## Operator buyruqlari (terminal)

| Buyruq | Nima qiladi |
|---|---|
| `python main.py login` | Telegram akkauntiga bir martalik kirish |
| `python main.py run` | Ilovani ishga tushiradi (Ctrl+C yoki SIGTERM bilan xavfsiz to'xtaydi) |
| `python main.py check` | Konfiguratsiya, PostgreSQL va migratsiyalarni tekshiradi |
| `python main.py check --app` | + ishlayotgan ilova heartbeat'i (userbot va bot) |
| `alembic upgrade head` | Baza sxemasini yangilaydi |
| `scripts/backup_db.sh [--docker]` | Zaxira nusxa oladi |
| `scripts/restore_db.sh FAYL [--docker]` | Zaxiradan tiklaydi (tasdiqlash so'raladi) |

`check` chiqish kodlari: `0` — hammasi joyida, `1` — baza, migratsiya yoki ilova muammosi,
`2` — `.env` dagi xato.
