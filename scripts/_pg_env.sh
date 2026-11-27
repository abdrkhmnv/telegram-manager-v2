#!/usr/bin/env bash
# DATABASE_URL ni PG* muhit o'zgaruvchilariga aylantiradi.
# Parol buyruq satrida ko'rinmasligi uchun (ps orqali) PGPASSWORD ishlatiladi.
# Faqat boshqa skriptlar tomonidan "source" qilinadi.

load_pg_env() {
    if [[ -z "${DATABASE_URL:-}" && -f .env ]]; then
        set -a
        # shellcheck disable=SC1091
        . ./.env
        set +a
    fi
    : "${DATABASE_URL:?DATABASE_URL kerak: .env yoki muhit oʻzgaruvchisi}"

    local exports
    exports="$(
        python3 - <<'PY'
import os, shlex
from urllib.parse import unquote, urlsplit

url = urlsplit(os.environ["DATABASE_URL"].replace("+asyncpg", "", 1))
values = {
    "PGHOST": url.hostname or "localhost",
    "PGPORT": str(url.port or 5432),
    "PGUSER": unquote(url.username or ""),
    "PGPASSWORD": unquote(url.password or ""),
    "PGDATABASE": url.path.lstrip("/"),
}
for key, value in values.items():
    print(f"export {key}={shlex.quote(value)}")
PY
    )"
    eval "$exports"
}
