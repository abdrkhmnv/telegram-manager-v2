# Arxitektura

## Umumiy ko'rinish

```
            ┌──────────────┐   Bot API    ┌──────────────────────────┐
 Egasi ───► │ Control Bot  │ ───────────► │                          │
 (Telegram) └──────────────┘              │   Telegram Manager v2    │
                                          │  (bitta asyncio jarayon) │
            ┌──────────────┐   MTProto    │                          │
 Telegram ◄─│ Telethon     │ ◄─────────── │  servislar / modullar    │
            │ userbot      │              │  repozitoriylar          │
            └──────────────┘              └────────────┬─────────────┘
                                                       │ asyncpg
                                                ┌──────▼──────┐
                                                │ PostgreSQL  │  yagona haqiqat manbai
                                                └─────────────┘
```

- **Bitta akkaunt.** Ko'p akkauntli boshqaruv yo'q va rejalashtirilmagan.
- **Control Bot** — faqat interfeys. U hech qachon o'zi amal bajarmaydi; buyruqlarni
  servislarga uzatadi, servislar userbot orqali bajaradi.
- **PostgreSQL** — yagona holat manbai. Redis ishlatilmaydi: vazifalar navbati va
  qulflar ham PostgreSQL'da (pastga qarang).

## Qatlamlar

| Qatlam | Katalog | Mas'uliyat |
|---|---|---|
| Kirish nuqtasi | `main.py` | CLI (`run`, `check`), chiqish kodlari |
| Ilova | `app/` | Konfiguratsiya, komponentlarni yig'ish, lifecycle |
| Yadro | `core/` | Istisnolar; 2-bosqichdan userbot, control bot, event dispatcher |
| Bot UI | `bot/` *(2-bosqich)* | Handlerlar, klaviaturalar, callback'lar, holatlar |
| Modullar | `modules/` *(3–7)* | Forwarder, autopost, media va h.k. — biznes oqimlari |
| Servislar | `services/` *(3–7)* | Telegram amallari + repozitoriylar orasidagi mantiq |
| Ma'lumotlar | `database/` | Modellar, repozitoriylar, migratsiyalar, ulanish |
| Yordamchilar | `utils/` | Log, vaqt, validatsiya — tashqi bog'liqliksiz, to'liq test qilingan |

Qoidalar: yuqori qatlam pastkisini chaqiradi, aksincha emas; `utils/` hech narsaga bog'liq
emas; repozitoriylar `commit` qilmaydi — tranzaksiya chegarasi `Database.session()`.

## Lifecycle

`app/lifecycle.py` dagi `LifecycleManager` komponentlarni ro'yxat tartibida ishga
tushiradi va teskari tartibda to'xtatadi:

1. `DatabaseComponent` — ulanishni eksponensial backoff bilan kutadi (10 urinishgacha),
   so'ng sxema oxirgi migratsiyada ekanini tekshiradi. Eskirgan bo'lsa ilova
   ishga tushmaydi va `alembic upgrade head` ni bajarishni so'raydi.
2. *(2-bosqich)* `UserbotComponent`, `ControlBotComponent`, `SchedulerComponent`.

Biror komponent ishga tushmasa, oldin ishga tushganlari to'xtatiladi. SIGINT/SIGTERM
kelganda barcha komponentlar `stop_timeout` (30 s) ichida to'xtatiladi; osilib qolgan
komponent boshqalarini to'xtatishga xalaqit bermaydi.

## Rejalashtirish: PostgreSQL'dagi lease

APScheduler o'rniga bazaga asoslangan oddiy va ishonchli mexanizm tanlangan:

```sql
UPDATE autopost_tasks SET locked_by = :worker, locked_until = :now + :lease
WHERE id IN (
    SELECT id FROM autopost_tasks
    WHERE status = 'active' AND next_run_at <= :now
      AND (locked_until IS NULL OR locked_until < :now)
    ORDER BY next_run_at LIMIT :n
    FOR UPDATE SKIP LOCKED)
RETURNING *;
```

- **Takroriy bajarilish yo'q:** `SKIP LOCKED` — ikki ishchi bitta vazifani ololmaydi.
- **Qayta ishga tushganda tiklanish:** jarayon qulasa, `locked_until` o'tgach vazifa
  avtomatik qayta egallanadi. Holat (keyingi vaqt, xatolar soni) bazada saqlanadi.
- **Idempotentlik:** har bir bajarilish `scheduled_posts` ga `(task_id, manzil, vaqt)`
  noyob kaliti bilan yoziladi; forward'lar `forward_logs` ga
  `(qoida, manba chat, xabar, manzil)` kaliti bilan. Lease takrorlansa ham
  bir xabar ikki marta yuborilmaydi.
- **Faqat egasi bo'shatadi:** `release()` faqat `locked_by` mos kelsa ishlaydi.

Bu xatti-harakat integratsion testlarda (parallel ishchilar, lease tugashi) tekshiriladi.

## Vaqt

- Bazada barcha vaqtlar `TIMESTAMP WITH TIME ZONE`, UTC; ulanish `timezone=UTC` bilan ochiladi.
- `time_of_day`, `active_from/active_to` — mahalliy (Asia/Tashkent) devor soati.
- `utils/time_utils.py` naive `datetime` ni qabul qilmaydi; kunlik/haftalik/tasodifiy
  keyingi vaqt hisoblari va faol soatlar (yarim tundan o'tuvchi oynalar ham) shu yerda.

## Loglash

- Standart `logging` + o'zimizning `JsonFormatter` (qo'shimcha bog'liqliksiz).
- Har bir yozuv `SecretRedactor` dan o'tadi: bot tokeni naqshi, URL'dagi parol va
  `register_secret()` orqali ro'yxatga olingan qiymatlar `***` bo'ladi.
- Fayl loglari aylanadi: 10 MB × 5.

## Muhim dizayn qarorlari

| Qaror | Sabab |
|---|---|
| Redis yo'q | Hajm kichik; PostgreSQL navbat/qulf vazifasini bajara oladi; bitta manba |
| APScheduler o'rniga DB lease | Persistent, restart'dan keyin tiklanadi, concurrency semantikasi aniq |
| Enum = `VARCHAR(32)` + `CHECK` | Yangi qiymat qo'shish oddiy migratsiya, native ENUM ALTER muammolarisiz |
| Loglarda chat ID — Telegram ID | Chat keshidan o'chirilsa ham tarix va statistika saqlanadi |
| Sozlamalar 3 guruhda | `alembic` va `check` Telegram kalitlarisiz ishlay oladi |
| Relationship'lar `lazy="raise"` | Async kontekstda yashirin so'rovlar bo'lmaydi — xato darhol ko'rinadi |
