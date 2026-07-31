#!/bin/sh

set -e

BACKUP_FILE="firefly-$(date +%Y-%m-%d_%H-%M-%S).sql.gz"
WEB_BACKUP_FILE="web-$(date +%Y-%m-%d_%H-%M-%S).sql.gz"
echo "DB debug: DB_CONNECTION='${DB_CONNECTION}' DB_HOST='${DB_HOST}' DB_PORT='${DB_PORT}' DB_DATABASE='${DB_DATABASE}' DB_USERNAME='${DB_USERNAME}' DB_FILE='${DB_FILE}'"
echo "exporting database ${DB_CONNECTION}"

case "${DB_CONNECTION}" in

  mysql)
    BACKUP_FILE_RAW="${BACKUP_FILE%.gz}"
    mysqldump --host="${DB_HOST}" --port="${DB_PORT}" --user="${DB_USERNAME}" --password="${DB_PASSWORD}" "${DB_DATABASE}" > "${BACKUP_FILE_RAW}"
    WEB_BACKUP_FILE_RAW="${WEB_BACKUP_FILE%.gz}"
    mysqldump --host="${DB_HOST}" --port="${DB_PORT}" --user="${WEB_DB_USER}" --password="${WEB_DB_PASSWORD}" "${WEB_DB_NAME}" > "${WEB_BACKUP_FILE_RAW}"
    gzip -c "${BACKUP_FILE_RAW}" > "${BACKUP_FILE}"
    rm -f "${BACKUP_FILE_RAW}"
    gzip -c "${WEB_BACKUP_FILE_RAW}" > "${WEB_BACKUP_FILE}"
    rm -f "${WEB_BACKUP_FILE_RAW}"
    ;;

  postgres)
    export PGPASSWORD="${DB_PASSWORD}"
    BACKUP_FILE_RAW="${BACKUP_FILE%.gz}"
    pg_dump --host="${DB_HOST}" --port="${DB_PORT}" --dbname="${DB_DATABASE}" --username="${DB_USERNAME}" --no-password > "${BACKUP_FILE_RAW}"
    gzip -c "${BACKUP_FILE_RAW}" > "${BACKUP_FILE}"
    rm -f "${BACKUP_FILE_RAW}"
    ;;

  sqlite)
    # create sqlite backup then gzip it
    BACKUP_FILE_UNCOMPRESSED="$(date +%Y-%m-%d_%H-%M-%S).sqlite"
    sqlite3 "/database/${DB_FILE}" ".backup '${BACKUP_FILE_UNCOMPRESSED}'"
    gzip "${BACKUP_FILE_UNCOMPRESSED}"
    BACKUP_FILE="${BACKUP_FILE_UNCOMPRESSED}.gz"
    ;;

  *)
    echo "invalid database type provided"
    exit 1
    ;;

esac

# Export failures will stop the script due to 'set -e'

echo "uploading file"

rclone copy "${BACKUP_FILE}" "${RCLONE_REMOTE}:${BACKUP_FOLDER}"
if [ "$?" != 0 ]; then
  echo "rclone copy failed"
  exit 1
fi

echo "deleting local backup file"

rm -f "${BACKUP_FILE}"

echo "deleting any old backups"

rclone delete --min-age "${BACKUP_AGE}"d --include "*.{sql,sqlite,sql.gz,sqlite.gz}" "${RCLONE_REMOTE}:${BACKUP_FOLDER}"

echo "done"
echo "==================================="
