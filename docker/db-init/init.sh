#!/bin/sh
set -eu

# Initialization script for MariaDB that uses environment variables.
# Expected env vars (can be set in .db.env):
#   MYSQL_ROOT_PASSWORD (required)
#   WEB_DB_NAME, WEB_DB_USER, WEB_DB_PASSWORD

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required to run init scripts}"

DB_NAME="${WEB_DB_NAME:-bank_transactions}"
DB_USER="${WEB_DB_USER:-bank_transactions_user}"
DB_PASS="${WEB_DB_PASSWORD:-ReplaceWithStrongPassword}"

echo "[init.sh] Creating database '${DB_NAME}' and user '${DB_USER}'"

# Write SQL to a temporary file to avoid heredoc line-ending issues on Windows hosts.
TMP_SQL=/tmp/init_bank_db.sql
cat > "$TMP_SQL" <<'SQL'
CREATE DATABASE IF NOT EXISTS `DB_NAME_PLACEHOLDER` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'DB_USER_PLACEHOLDER'@'%' IDENTIFIED BY 'DB_PASS_PLACEHOLDER';
GRANT ALL PRIVILEGES ON `DB_NAME_PLACEHOLDER`.* TO 'DB_USER_PLACEHOLDER'@'%';
FLUSH PRIVILEGES;
SQL

# Replace placeholders safely
sed -i "s/DB_NAME_PLACEHOLDER/$(printf '%s' "$DB_NAME" | sed 's/[\/&]/\\&/g')/g" "$TMP_SQL"
sed -i "s/DB_USER_PLACEHOLDER/$(printf '%s' "$DB_USER" | sed 's/[\/&]/\\&/g')/g" "$TMP_SQL"
sed -i "s/DB_PASS_PLACEHOLDER/$(printf '%s' "$DB_PASS" | sed 's/[\/&]/\\&/g')/g" "$TMP_SQL"

# Use whatever client is available: mysql or mariadb. If none found, print a warning.
if command -v mysql >/dev/null 2>&1; then
	mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" < "$TMP_SQL"
elif command -v mariadb >/dev/null 2>&1; then
	mariadb -uroot -p"${MYSQL_ROOT_PASSWORD}" < "$TMP_SQL"
else
	echo "[init.sh] WARNING: no 'mysql' or 'mariadb' client found; cannot initialize DB here."
	echo "[init.sh] SQL that would have been executed:" 
	sed -n '1,200p' "$TMP_SQL"
fi

echo "[init.sh] Done."
