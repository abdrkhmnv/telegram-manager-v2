#!/usr/bin/env bash
# Zaxira nusxadan tiklash. DIQQAT: joriy ma'lumotlar zaxiradagisi bilan almashtiriladi.
#
# Foydalanish:
#   scripts/restore_db.sh backups/tgmanager_....dump
#   scripts/restore_db.sh backups/tgmanager_....dump --docker
#
# Tiklashdan oldin ilovani to'xtating (docker compose stop app).
set -euo pipefail
cd "$(dirname "$0")/.."

DUMP="${1:?Zaxira fayli yoʻli kerak}"
MODE="${2:-}"
[[ -f "$DUMP" ]] || { echo "XATO: fayl topilmadi: $DUMP" >&2; exit 1; }

read -r -p "Joriy baza '$DUMP' bilan almashtiriladi. Davom etish uchun HA deb yozing: " answer
[[ "$answer" == "HA" ]] || { echo "Bekor qilindi."; exit 1; }

if [[ "$MODE" == "--docker" ]]; then
    docker compose exec -T db sh -c \
        'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction' \
        <"$DUMP"
else
    # shellcheck source=scripts/_pg_env.sh
    . scripts/_pg_env.sh
    load_pg_env
    pg_restore --dbname="$PGDATABASE" --clean --if-exists --no-owner --single-transaction "$DUMP"
fi
echo "Tiklandi. Endi bajaring: alembic upgrade head && python main.py check"
