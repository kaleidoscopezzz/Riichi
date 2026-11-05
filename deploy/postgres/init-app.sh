#!/bin/sh
# Only on a NEW PostgreSQL volume: create the non-superuser application owner.
# This is role/bootstrap setup, not a Django migration or administrator account.
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 \
    --set=app_user="$RIICHI_DB_USER" --set=app_password="$RIICHI_DB_PASSWORD" --set=app_db="$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_user', :'app_password') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'app_db', :'app_user') \gexec
SQL
