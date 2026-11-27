# Foydalanish qo'llanmasi

## Boshlash

1. `.env` ni to'ldiring (README → *Telegram API sozlash*).
2. Telegram'da botingizga bir marta `/start` yozing.
3. Serverda bir marta: `python main.py login` (Docker:
   `docker compose run --rm app python main.py login`).
4. Ilovani ishga tushiring: `python main.py run` (Docker: `docker compose up -d`).
5. Botga `/start` yozing → **💬 Chatlar → 🔄 Yangilash** — akkauntdagi dialoglar yuklanadi.

Bot **faqat** `OWNER_TELEGRAM_ID` egasiga va faqat bot bilan shaxsiy chatda javob beradi.
Boshqa odamlar yozsa, bot umuman javob bermaydi. Barcha vaqtlar **Asia/Tashkent** bo'yicha.

## Umumiy qoidalar

- **⬅️ Orqaga** — oldingi bo'lim, **🏠 Bosh menyu** — bosh menyu. `/start` istalgan
  jarayonni bekor qilib, bosh menyuni ochadi.
- Bot yangi xabar yubormasdan mavjud panel xabarini o'zgartiradi — chat to'lib ketmaydi.
- Tugmani tez ikki marta bossangiz, ikkinchisi e'tiborsiz qoldiriladi.
- Eski xabardagi tugma ishlamasa ("Bu tugma eskirgan"), bosh menyu qayta ochiladi.
- O'chirish, bekor qilish va yuborish kabi amallar **tasdiqlashni** so'raydi.

## 📤 Xabar yuborish

1. Chatlarni tanlang (✅ belgisi), **➡️ Davom etish**.
2. Xabarni yuboring: matn, rasm, video, GIF, hujjat, audio yoki ovozli xabar.
   Bir nechta rasm/video — albom (10 tagacha). Formatlash (qalin, kursiv, havola) saqlanadi.
3. **👁 Ko'rib chiqish** — bot xabarni sizga qanday ko'rinishini yuboradi.
4. **✅ Yuborish** — chatlarga navbat bilan yuboriladi, jarayon "⏳ 3/10" ko'rinishida.
   Oxirida natija: nechta yuborildi va qaysi chatga nima sababdan yuborilmadi.

Faqat akkauntingiz dialoglaridagi (allaqachon yozishgan yoki a'zo bo'lgan) chatlarga
yuborish mumkin — notanish odamlarga xabar yuborilmaydi. Bitta yuborishda 50 tagacha chat.

## 🔁 Forwarder

**➕ Yangi qoida**: nom → rejim → manba chatlar → manzil chatlar.

| Rejim | Natija |
|---|---|
| ↪️ Native forward | Telegram'ning oddiy forward'i, manba ko'rsatiladi |
| 📄 Copy | Yangi xabar sifatida (forward sarlavhasisiz), formatlash va media saqlanadi; sarlavha/izoh qo'shish mumkin |

Qoida sahifasida:
- **⏸ Pauza / ▶️ Davom ettirish**, **⛔ O'chirib qo'yish / ✅ Yoqish**.
- **🔤 Kalit so'zlar** — har qatorda: `+aksiya, chegirma` (shulardan biri bo'lsa),
  `-reklama` (bo'lsa — yuborilmaydi), `0` — tozalash.
- **🎞 Media turlari** — faqat tanlangan turlar (hech biri tanlanmasa — hammasi).
- **♻️ Takror** — oxirgi 24 soatda shu manzilga yuborilgan bir xil kontent o'tkazib yuboriladi.
- **📝 Sarlavha / Izoh** (faqat Copy) — xabar boshiga/oxiriga qo'shiladi.
- **📋 Loglar** — oxirgi yetkazishlar: ✅ yuborildi, ❌ xato (sababi bilan), ⏭ o'tkazildi.

Himoyalangan (nusxalash taqiqlangan) kontent hech qaysi rejimda yuborilmaydi. Bir xabar
bir qoida bo'yicha bir manzilga faqat bir marta yetkaziladi. Forwarder'ning o'zi yuborgan
xabarlar qayta yo'naltirilmaydi (halqa bo'lmaydi). Manba va manzil bir xil bo'lishi mumkin emas.

## 📅 Autopost

**➕ Yangi post**: mazmun → chatlar → qachon:

| Tanlov | Kiritish |
|---|---|
| 1️⃣ Bir marta | `28.11.2026 09:30` |
| 🔁 Har kuni | `09:30` |
| 📆 Har hafta | kunlarni belgilab, so'ng `09:30` |

Post sahifasida: **⏸/▶️**, **👁 Ko'rish**, **✏️ Kontentni almashtirish**, **🚫 Bekor qilish**,
**🗑 O'chirish**. Ilova o'chiq bo'lgan paytdagi kunlik/haftalik postlar keyinroq
"to'plab" yuborilmaydi — keyingi vaqtdan davom etadi. Bir martalik post kechiksa —
ilova ishga tushgach yuboriladi. Xato bo'lsa, o'sha post faqat xato bo'lgan chatlarga
2, 4 daqiqadan keyin qayta yuboriladi (jami 3 urinish).

## 🎲 Random Autopost

**➕ Yangi vazifa**: chatlar → oraliq (daqiqa, masalan `60-180`) → faol soatlar
(`09:00-22:00` yoki `0` — kun bo'yi) → navbat uchun postlar (har bir xabar yoki albom
— alohida post) → **✅ Saqlash**.

Har safar navbatdagi eng kam yuborilgan postlardan biri tanlanadi, oxirgi yuborilgani
ketma-ket takrorlanmaydi. Keyingi vaqt belgilangan oraliqdan tasodifiy tanlanadi va faol
soatlardan tashqariga tushsa, keyingi faol oyna boshiga suriladi. **➕ Post qo'shish**
bilan navbatni to'ldirish mumkin.

## 🖼 Media Manager

Yuborilgan va yuklangan barcha fayllar. **➕ Yuklash** — fayllarni bevosita kutubxonaga
qo'shish. Fayl sahifasida: hajmi, turi, qaysi postlarda ishlatilgani, **👁 Ko'rish**,
**🗑 O'chirish** (rejalashtirilgan postda ishlatilayotgan fayl o'chirilmaydi). Bir xil fayl
ikki marta saqlanmaydi. Hajm chegarasi — 20 MB (Bot API cheklovi).

## 💬 Chatlar · 👥 Guruhlar · 📢 Kanallar · 🔎 Qidiruv

Ro'yxatlar sahifalangan, ⭐ saqlanganlar birinchi. Chat sahifasida: turi, ID, username,
a'zolar soni, **⭐ Saqlash**, **🏷 Toifalar**. **🔄 Yangilash** dialoglarni qayta yuklaydi;
akkaunt chiqib ketgan chatlar "⚠️ oxirgi yangilashda topilmadi" deb belgilanadi va
tanlov ro'yxatlarida ko'rinmaydi. **🔎 Qidiruv** — nom yoki @username bo'yicha.

## 📊 Statistika

Faqat bazadagi haqiqiy yozuvlardan: yuborilgan xabarlar, native forward'lar, copy
yetkazishlar, rejalashtirilgan va random postlar, muvaffaqiyatli/xato amallar — jami va
bugun; oxirgi 7 kun grafigi; faol va pauzadagi vazifalar/qoidalar.

## ⚙️ Sozlamalar

- **ℹ️ Tizim holati** — userbot, PostgreSQL, migratsiya, forwarder, rejalashtiruvchi va
  Control Bot holati, versiya, ish vaqti.
- **🏷 Toifalar** — toifalar ro'yxati, ulardagi chatlar, o'chirish.
- **📜 Yuborilgan xabarlar tarixi** — panel orqali yuborilgan xabarlar: **✏️ Matnni
  tahrirlash**, **🗑 O'chirish** (hamma uchun, tasdiqlash bilan).

## Operator buyruqlari (terminal)

| Buyruq | Nima qiladi |
|---|---|
| `python main.py login` | Telegram akkauntiga bir martalik kirish |
| `python main.py run` | Ilovani ishga tushiradi (Ctrl+C yoki SIGTERM bilan xavfsiz to'xtaydi) |
| `python main.py check` | Konfiguratsiya, PostgreSQL va migratsiyalarni tekshiradi |
| `python main.py check --app` | + ishlayotgan ilova heartbeat'i |
| `alembic upgrade head` | Baza sxemasini yangilaydi |
| `scripts/backup_db.sh [--docker]` | Zaxira nusxa oladi |
| `scripts/restore_db.sh FAYL [--docker]` | Zaxiradan tiklaydi (tasdiqlash so'raladi) |
