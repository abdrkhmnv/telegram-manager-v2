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
2. `UserbotComponent` (`core/userbot.py`) — Telethon klienti. Sessiya katalogi `700`,
   fayl `600`. Avtorizatsiya yo'q bo'lsa `python main.py login` ni so'rab to'xtaydi.
   Telethon'ning o'z qayta ulanishiga qo'shimcha watchdog: ulanish yo'qolsa backoff
   (30 s → 5 daqiqagacha) bilan qayta ulanadi.
3. `ControlBotComponent` (`core/control_bot.py`) — aiogram 3. Ishga tushishda tokenni
   `getMe` bilan tekshiradi, buyruqlarni faqat egasi chatiga o'rnatadi va polling'ni
   alohida task'da boshlaydi (tarmoq xatolarida aiogram o'zi backoff qiladi).
4. `HeartbeatComponent` (`app/health.py`) — har 30 soniyada `storage/health.json` ga
   komponentlar holatini yozadi; `main.py check --app` (Docker healthcheck) uni o'qiydi.
5. `ForwarderComponent` (`services/forwarding_service.py`) — Telethon `NewMessage` va `Album`
   hodisalarini tinglaydi, faol qoidalarni xotirada saqlaydi (o'zgarishda va har 60 s da
   qayta yuklanadi), har bir yetkazishni `forward_logs` da idempotent band qiladi.
6. `SchedulerComponent` (`services/scheduling_service.py`) — har 15 s da vaqti kelgan
   vazifalarni lease bilan egallaydi va bajaradi.

Haqiqiy tartib: baza → userbot → forwarder → rejalashtiruvchi → Control Bot → heartbeat.

## Control Bot ichki tuzilishi

```
Update ─► UserContextMiddleware (aiogram) ─► OwnerOnlyMiddleware ─► routerlar
                                               │ egasi emas / guruh → jim tashlanadi
callback_query ─► CallbackGuardMiddleware ─► NavCallback.filter() ─► on_navigate
                   │ double tap → e'tiborsiz     │ mos kelmasa → on_unknown_callback
                   │ parallel → "kuting"         │   (eskirgan tugma → bosh menyu)
```

- `bot/callbacks.py` — `NavCallback` (`nav:<bo'lim>:<sahifa>`), har biri ≤ 64 bayt (testda tekshiriladi).
- `bot/screens.py` — sof funksiyalar: `Screen(text, markup)`. Tarmoqsiz test qilinadi.
- `bot/rendering.py` — panel xabari tahrirlanadi; "not modified" jim o'tkaziladi,
  tahrirlab bo'lmasa yangi xabar yuboriladi.
- `bot/storage.py` — `PostgresStorage`: FSM holati `bot_fsm_states` jadvalida.
- Bog'liqliklar (`status_service`, `timezone`) dispatcher `workflow_data` orqali beriladi.

Biror komponent ishga tushmasa, oldin ishga tushganlari to'xtatiladi. SIGINT/SIGTERM
kelganda barcha komponentlar `stop_timeout` (30 s) ichida to'xtatiladi; osilib qolgan
komponent boshqalarini to'xtatishga xalaqit bermaydi.

## Panel oqimlari

- `bot/picker.py` — qayta ishlatiladigan ko'p tanlovli chat tanlash; tanlov FSM'da,
  "Davom etish" joriy holat uchun ro'yxatdan o'tgan davom handlerini chaqiradi.
- `bot/collect.py` — matn va media (albom) yig'ish: Bot API'dan yuklab olish, tekshirish,
  `MediaService` orqali saqlash, holat xabarini tahrirlash.
- `bot/middleware/user_lock.py` — albom qismlari bir vaqtda kelganda FSM'ga yozish
  to'qnashmasligi uchun bir foydalanuvchi xabarlari ketma-ket ishlanadi.
- Handlerlar faqat `Services` (`bot/context.py`) orqali ishlaydi — testlarda soxta
  servislar bilan haqiqiy Dispatcher sinovdan o'tkaziladi.

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
- **Retry:** xato bo'lsa `next_run_at` o'zgarmaydi, `locked_until` keyingi urinish
  vaqtiga qo'yiladi (2, 4 daqiqa ...). Xuddi shu slot qayta bajarilganda muvaffaqiyatli
  manzillar o'tkazib yuboriladi, faqat xato bo'lganlariga qayta yuboriladi.
- **O'tkazib yuborilgan slotlar:** ilova o'chiq bo'lgan paytdagi kunlik/haftalik slotlar
  to'planib yuborilmaydi — bitta bajarilishdan so'ng keyingi slot hozirgi vaqtdan hisoblanadi.

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
