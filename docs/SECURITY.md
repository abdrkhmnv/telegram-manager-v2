# Xavfsizlik

## Nimani himoya qilamiz

| Aktiv | Xavf | Himoya |
|---|---|---|
| Telethon sessiya fayli | Sessiya = akkauntga to'liq kirish | Git'dan tashqarida, katalog `700`, faqat ilova foydalanuvchisi |
| `BOT_TOKEN` | Boshqa odam botni boshqaradi | `.env` (`600`), loglarda yashiriladi |
| `TELEGRAM_API_HASH` | Ilova nomidan so'rovlar | `.env`, `SecretStr`, loglarda yashiriladi |
| `DATABASE_URL` paroli | Bazaga kirish | `.env`, `SecretStr`, loglarda yashiriladi, port tashqariga ochilmaydi |
| Boshqaruv paneli | Begona odam buyruq beradi | Har bir update'da `OWNER_TELEGRAM_ID` tekshiruvi, faqat shaxsiy chat |

## Qoidalar

1. **Maxfiy qiymatlar faqat muhit o'zgaruvchilarida** (`.env`). Ular kodda, bazada,
   Git'da va loglarda bo'lmaydi. `.env.example` da faqat bo'sh/namuna qiymatlar.
2. **Fayl ruxsatlari:** `chmod 600 .env`, `chmod 700 storage storage/sessions`.
   Ilova saqlash katalogini o'zi `700` bilan yaratadi; Docker image root'siz ishlaydi.
3. **Loglar:** `utils/logger.py` bot tokeni naqshini, `scheme://user:parol@` dagi parolni
   va `register_secret()` bilan ro'yxatga olingan qiymatlarni `***` ga almashtiradi.
   Shunga qaramay yangi kodda maxfiy qiymatni log'ga uzatmang.
4. **Konfiguratsiya xatolari** qiymatni ko'rsatmaydi (`hide_input_in_errors`).
5. **SQL:** faqat ORM va parametrlangan so'rovlar. `LIKE` qidiruvida `%` va `_` ekranlanadi.
6. **Fayl yo'llari:** `utils.validators.safe_storage_path` — mutlaq yo'llar, `..` va
   saqlash katalogidan tashqariga olib chiquvchi symlinklar rad etiladi.
7. **Buyruq bajarish yo'q:** panel orqali ixtiyoriy shell buyrug'i bajarilmaydi.
8. **Avtorizatsiya:** `bot/middleware/owner.py` dispatcher darajasidagi outer middleware —
   har qanday handler va filtrdan oldin, barcha update turlari uchun ishlaydi. Faqat
   Telegram bergan yuboruvchi ID'si `OWNER_TELEGRAM_ID` bilan solishtiriladi; callback
   ma'lumotiga hech qachon ishonilmaydi. Guruh/kanaldagi xabarlar egasidan bo'lsa ham
   rad etiladi. Begonalarga hech qanday javob berilmaydi (bot borligini oshkor qilmaslik
   uchun); urinishlar logga yoziladi (bir foydalanuvchi uchun daqiqada ko'pi bilan bir marta).
   Takroriy tugma bosilishi e'tiborsiz qoldiriladi va bir foydalanuvchining callback'lari
   ketma-ket bajariladi. Xavfli amallar uchun tasdiqlash keyingi bosqichlarda qo'shiladi.
9. **Kirish ma'lumotlari:** `python main.py login` telefon, kod va 2FA parolini faqat
   terminalda so'raydi; parol ekranda ko'rinmaydi; hech biri log yoki bazaga yozilmaydi.
10. **Telegram qoidalariga rioya:** tizim FloodWait'ni hurmat qiladi, cheklovlar,
   anti-spam mexanizmlari, maxfiylik sozlamalari va himoyalangan kontentni chetlab
   o'tmaydi, notanish odamlarga so'ralmagan xabar yubormaydi. Tasodifiy interval —
   foydalanuvchi belgilagan oraliq, anti-spam'ni aylanib o'tish vositasi emas.

## Kalitlar sizib chiqsa — almashtirish tartibi

**Bot tokeni:** @BotFather → `/mybots` → bot → *API Token* → *Revoke current token*.
Yangi tokenni `.env` ga yozing, ilovani qayta ishga tushiring.

**Telethon sessiyasi (eng xavflisi):** Telegram → *Sozlamalar → Qurilmalar* →
noma'lum sessiyalarni tugating (yoki *Boshqa barcha seanslarni tugatish*).
Serverdagi `storage/sessions/*.session` faylini o'chiring va qayta kiring.
Ikki bosqichli tekshiruv (bulutli parol) yoqilganiga ishonch hosil qiling.

**API ID / hash:** faqat o'zi bilan akkauntga kirib bo'lmaydi, lekin sizib chiqqan
bo'lsa sessiyalarni tugating va https://my.telegram.org dagi ilova ma'lumotlarini
tekshiring. Yangi sessiya yaratishda yangi kalitlardan foydalaning.

**PostgreSQL paroli:**

```bash
# Docker ("tgmanager" o'rniga .env dagi POSTGRES_USER va POSTGRES_DB qiymatlari)
docker compose exec db psql -U tgmanager -d tgmanager \
  -c "ALTER USER tgmanager WITH PASSWORD 'YANGI_KUCHLI_PAROL';"
# .env dagi POSTGRES_PASSWORD (va DATABASE_URL) ni yangilang, so'ng:
docker compose up -d
```

**Git'ga tasodifan commit qilinsa:** faylni o'chirish yetarli emas — tarixda qoladi.
Avval kalitni yuqoridagidek **almashtiring**, keyin tarixni tozalang
(`git filter-repo`) va GitHub'da *Secret scanning* ogohlantirishlarini tekshiring.

## Xavfsizlik muammosi haqida xabar berish

Repozitoriy egasiga shaxsiy xabar orqali yozing; ochiq issue'da maxfiy ma'lumot qoldirmang.

## 8-bosqich tahlili

| Tekshirilgan joy | Natija |
|---|---|
| Avtorizatsiya | Har bir update outer middleware'da tekshiriladi (`OwnerOnlyMiddleware`); testlar begona xabar/callback va guruhdagi xabarlar hech qanday so'rov yubormasligini tasdiqlaydi |
| Callback ma'lumoti | Faqat bazadagi ichki ID va qisqa kodlar; har biri ≤ 64 bayt; buzilgan yoki eskirgan ma'lumot bosh menyuga qaytaradi; Telegram amali hech qachon to'g'ridan-to'g'ri callback'dan bajarilmaydi |
| Takroriy bajarish | Double tap e'tiborsiz; foydalanuvchi callback'lari ketma-ket; yuborish tasdiqlangach FSM darhol tozalanadi — qayta bosish ikkinchi yuborishga olib kelmaydi |
| Xavfli amallar | O'chirish, bekor qilish va yuborish — tasdiqlash oynasi bilan |
| Kirish ma'lumotlari | Chat ID, username, sana/vaqt, interval, kalit so'zlar, matn uzunligi tekshiriladi; taklif havolalari rad etiladi |
| Fayllar | MIME va hajm tekshiruvi (Bot API chegarasi 20 MB), bajariladigan fayllar rad etiladi, nom diskda ishlatilmaydi (SHA-256 asosida), barcha yo'llar `safe_storage_path` orqali, fayl ruxsati `600`, vaqtinchalik fayllar har doim o'chiriladi |
| SQL | Faqat ORM/parametrlangan so'rovlar; `LIKE` ekranlanadi; array parametrlari bind orqali |
| Telegram qoidalari | Yuborishlar ketma-ket va kechikish bilan; FloodWait hurmat qilinadi, uzoq kutish talab qilinsa amal to'xtatiladi; himoyalangan kontent o'tkaziladi; yuborish faqat akkaunt dialoglaridagi chatlarga |
| Halqalar | Forwarder o'zi yuborgan xabarlarni qayta yo'naltirmaydi; manba va manzil bir xil bo'lolmaydi |
| Resurslar | Navbatlar cheklangan (forward task'lar ≤ 200, lock lug'atlari ≤ 1000), event loop'ni to'xtatuvchi katta fayl xeshlash thread'da |
| Loglar | Xabar matni loglarga yozilmaydi (faqat ID va xato turi); tarix uchun bazada 100 belgilik qisqa matn saqlanadi |

Qolgan xavflar: server (VPS) ga kirish huquqi bor odam sessiya fayli orqali akkauntga
kira oladi — serverni himoyalang (SSH kalit, yangilanishlar, faqat kerakli portlar).
