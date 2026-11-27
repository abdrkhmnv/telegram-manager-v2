# Foydalanish qo'llanmasi

> **Joriy holat (1-bosqich):** Telegram boshqaruv paneli hali yo'q — u 2-bosqichda
> qo'shiladi va bu qo'llanma o'shanda to'ldiriladi. Hozircha quyidagi
> operator buyruqlari mavjud.

## Operator buyruqlari

| Buyruq | Nima qiladi |
|---|---|
| `python main.py check` | Konfiguratsiya, PostgreSQL ulanishi va migratsiyalarni tekshiradi |
| `python main.py run` | Ilovani ishga tushiradi (Ctrl+C yoki SIGTERM bilan xavfsiz to'xtaydi) |
| `alembic upgrade head` | Baza sxemasini yangilaydi |
| `scripts/backup_db.sh [--docker]` | Zaxira nusxa oladi |
| `scripts/restore_db.sh FAYL [--docker]` | Zaxiradan tiklaydi (tasdiqlash so'raladi) |

`check` chiqish kodlari: `0` — hammasi joyida, `1` — baza yoki migratsiya muammosi,
`2` — `.env` dagi xato.

## Rejalashtirilgan panel (2-bosqichdan)

Panel faqat `OWNER_TELEGRAM_ID` egasiga javob beradi. Bosh menyu:

| Tugma | Bo'lim |
|---|---|
| 📤 Xabar yuborish | Bir yoki bir nechta chatga matn/media yuborish, oldindan ko'rish |
| 🔁 Forwarder | Native va copy rejimidagi forward qoidalari |
| 📅 Autopost | Bir martalik, kunlik, haftalik postlar |
| 🎲 Random Autopost | Belgilangan oraliqda tasodifiy vaqtda navbatdan post |
| 🖼 Media Manager | Saqlangan media fayllar |
| 💬 Chatlar · 👥 Guruhlar · 📢 Kanallar | Dialoglar ro'yxati, qidiruv, toifalar |
| 🔎 Qidiruv | Chatlarni nom yoki username bo'yicha topish |
| 📊 Statistika | Bazadagi haqiqiy yozuvlar asosidagi hisobotlar |
| ⚙️ Sozlamalar | Ish vaqtidagi sozlamalar |
| ❓ Yordam | Qisqa yo'riqnoma |

Barcha vaqtlar panelda Asia/Tashkent bo'yicha ko'rsatiladi.
