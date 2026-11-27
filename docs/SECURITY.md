# Xavfsizlik

## Nimani himoya qilamiz

| Aktiv | Xavf | Himoya |
|---|---|---|
| Telethon sessiya fayli | Sessiya = akkauntga to'liq kirish | Git'dan tashqarida, katalog `700`, faqat ilova foydalanuvchisi |
| `BOT_TOKEN` | Boshqa odam botni boshqaradi | `.env` (`600`), loglarda yashiriladi |
| `TELEGRAM_API_HASH` | Ilova nomidan so'rovlar | `.env`, `SecretStr`, loglarda yashiriladi |
| `DATABASE_URL` paroli | Bazaga kirish | `.env`, `SecretStr`, loglarda yashiriladi, port tashqariga ochilmaydi |
| Boshqaruv paneli | Begona odam buyruq beradi | *(2-bosqich)* har bir xabar va callback'da `OWNER_TELEGRAM_ID` tekshiruvi |

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
8. **Avtorizatsiya (2-bosqich):** callback ma'lumotiga hech qachon avtorizatsiya sifatida
   ishonilmaydi; har bir update'da yuboruvchi ID'si `OWNER_TELEGRAM_ID` bilan solishtiriladi.
   Xavfli amallar tasdiqlashni talab qiladi; takroriy callback bosilishi bir marta bajariladi.
9. **Telegram qoidalariga rioya:** tizim FloodWait'ni hurmat qiladi, cheklovlar,
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
