# Ma'lumotlar bazasi

PostgreSQL 14+ (CI va Docker'da 16). SQLAlchemy 2.x async + asyncpg, migratsiyalar Alembic'da.

## Jadvallar

| Jadval | Vazifasi | Muhim cheklovlar |
|---|---|---|
| `settings` | Ish vaqtidagi kalit-qiymat sozlamalari (JSONB). **Maxfiy ma'lumot saqlanmaydi** | PK `key` |
| `chats` | Akkaunt kira oladigan dialoglar keshi | `uq_chats_telegram_id`, `chat_type` CHECK |
| `chat_categories` | Foydalanuvchi toifalari | `uq_chat_categories_name` |
| `chat_category_links` | Chat ↔ toifa (ko'p-ko'p) | Kaskad o'chirish |
| `forward_rules` | Forward qoidalari: `native` / `copy`, filtrlar, holat | `uq_forward_rules_name` |
| `forward_rule_sources`, `forward_rule_destinations` | Qoida ↔ manba/manzil chatlar | Kaskad o'chirish |
| `forward_logs` | Har bir yetkazib berish (idempotentlik + tarix) | `uq_forward_logs_delivery` |
| `media_files` | Media metama'lumotlari, nisbiy yo'l, SHA-256 | `uq_media_files_sha256`, `size_bytes >= 0` |
| `post_templates` | Qayta ishlatiladigan postlar | `parse_mode` ∈ {html, markdown} |
| `post_template_media` | Shablon mediasi (albom, 0..9 tartib) | Media o'chirishdan himoya (`RESTRICT`) |
| `autopost_tasks` | Rejalashtirilgan / tasodifiy vazifalar + lease | `random` ⇒ interval, `scheduled` ⇒ recurrence |
| `autopost_task_destinations` | Vazifa ↔ manzil chatlar | Kaskad o'chirish |
| `autopost_queue_items` | Tasodifiy autopost kontent navbati | `(task_id, template_id)` noyob |
| `scheduled_posts` | Har bir aniq bajarilish (occurrence) | `uq_scheduled_posts_occurrence` |
| `message_logs` | Yuborish/tahrir/o'chirish tarixi | `created_at` indeksi |
| `task_logs` | Fon vazifalari bajarilishi | `started_at` indeksi |
| `activity_logs` | Panel harakatlari auditi | `action`, `created_at` indekslari |
| `bot_fsm_states` | Control Bot suhbat holati (aiogram FSM), restart'dan keyin saqlanadi | PK `key` |

Migratsiyalar: `0001` — boshlang'ich sxema, `0002` — `bot_fsm_states`, `0003` —
`message_logs.preview` (tarix uchun qisqa matn) va `forward_rules.header_text/footer_text`
(copy rejimida sarlavha/izoh).

Statistika (7-bosqich) faqat shu jadvallardagi haqiqiy yozuvlardan hisoblanadi.

### Konvensiyalar

- Barcha vaqtlar `TIMESTAMP WITH TIME ZONE`, UTC.
- Nomlar: `pk_<jadval>`, `uq_<jadval>_<ustun>`, `ix_<jadval>_<ustun>`,
  `fk_<jadval>_<ustun>_<bog'langan jadval>`, `ck_<jadval>_<nom>`
  (`database/base.py: NAMING_CONVENTION`).
- Enumlar `VARCHAR(32)` + `CHECK (... IN (...))`; bazada `.value` saqlanadi.
- Log jadvallarida chatlar Telegram ID orqali saqlanadi (FK emas) — tarix yo'qolmaydi.

## Migratsiyalar

```bash
alembic upgrade head          # oxirgi versiyagacha
alembic current               # joriy versiya
alembic downgrade -1          # bitta orqaga (ehtiyot bo'ling!)
alembic upgrade head --sql    # SQL'ni bazaga ulanmasdan ko'rish
alembic check                 # modellar va migratsiyalar mosligini tekshirish
```

Ulanish manzili `DATABASE_URL` dan olinadi (`alembic.ini` da saqlanmaydi).

### Yangi migratsiya qo'shish

1. `database/models/` da modelni o'zgartiring.
2. `alembic revision --autogenerate -m "qisqa tavsif"`.
3. Yaratilgan faylni **qo'lda ko'rib chiqing** (autogenerate hamma narsani to'g'ri
   topmaydi: CHECK cheklovlari, server default'lar, ma'lumot ko'chirish).
4. `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` — ikki
   yo'nalishda ham ishlashini tekshiring.
5. `alembic check` — farq qolmaganini tasdiqlang. CI ham shuni tekshiradi.

Ishga tushishda ilova sxema versiyasini tekshiradi va eskirgan bazada ishlamaydi.

## Ulanishlar puli

`DB_POOL_SIZE` (5) + `DB_MAX_OVERFLOW` (5) — bitta jarayon uchun yetarli. `pool_pre_ping`
uzilgan ulanishlarni aniqlaydi, `pool_recycle=1800` eski ulanishlarni yangilaydi.
`DB_COMMAND_TIMEOUT` har bir so'rovga vaqt chegarasi qo'yadi.

## Zaxira nusxa va tiklash

```bash
# Docker Compose
scripts/backup_db.sh --docker
scripts/restore_db.sh backups/tgmanager_20261127T120000Z.dump --docker

# Mahalliy / VPS (DATABASE_URL yoki .env orqali)
scripts/backup_db.sh
scripts/restore_db.sh backups/tgmanager_20261127T120000Z.dump
```

- Zaxiralar `backups/` katalogiga `pg_dump --format=custom` bilan yoziladi (700/600 ruxsat).
  Parol buyruq satriga chiqmaydi (`PGPASSWORD` orqali uzatiladi).
- Tiklashdan oldin ilovani to'xtating (`docker compose stop app`). Skript `HA` deb
  tasdiqlashni so'raydi, so'ng `--clean --single-transaction` bilan tiklaydi.
- Tiklangandan keyin: `alembic upgrade head && python main.py check`.
- Zaxiralarni boshqa joyda ham saqlang va vaqti-vaqti bilan tiklashni sinab ko'ring.

Kundalik avtomatik zaxira (cron, VPS):

```cron
30 3 * * * cd /opt/telegram-manager-v2 && scripts/backup_db.sh --docker >> logs/backup.log 2>&1
```

Eski zaxiralarni tozalash: `find backups -name '*.dump' -mtime +14 -delete`.
