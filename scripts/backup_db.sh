#!/usr/bin/env bash
# PostgreSQL zaxira nusxasi (pg_dump, custom format).
#
# Foydalanish:
#   scripts/backup_db.sh            # mahalliy/VPS PostgreSQL (DATABASE_URL orqali)
#   scripts/backup_db.sh --docker   # docker compose ichidagi "db" xizmati
#
# Natija: backups/tgmanager_YYYYMMDDTHHMMSSZ.dump (faqat egasi o'qiy oladi)
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
OUT="$BACKUP_DIR/tgmanager_$(date -u +%Y%m%dT%H%M%SZ).dump"

if [[ "${1:-}" == "--docker" ]]; then
    docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' >"$OUT"
else
    # shellcheck source=scripts/_pg_env.sh
    . scripts/_pg_env.sh
    load_pg_env
    pg_dump --format=custom --file="$OUT"
fi

if [[ ! -s "$OUT" ]]; then
    rm -f "$OUT"
    echo "XATO: zaxira fayli bo'sh — pg_dump muvaffaqiyatsiz" >&2
    exit 1
fi
echo "Zaxira yaratildi: $OUT ($(du -h "$OUT" | cut -f1))"
