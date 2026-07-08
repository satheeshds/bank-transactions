#!/bin/sh

set -ex

BACKUP_FILE="$(date +%Y-%m-%d_%H-%M-%S).sql.gz"
echo "DB debug: DB_CONNECTION='${DB_CONNECTION}' DB_HOST='${DB_HOST}' DB_PORT='${DB_PORT}' DB_DATABASE='${DB_DATABASE}' DB_USERNAME='${DB_USERNAME}' DB_FILE='${DB_FILE}'"
echo "exporting database ${DB_CONNECTION}"

case "${DB_CONNECTION}" in

  mysql)
    mysqldump --host="${DB_HOST}" --port="${DB_PORT}" --user="${DB_USERNAME}" --password="${DB_PASSWORD}" "${DB_DATABASE}" | gzip > "${BACKUP_FILE}"
    ;;

  postgres)
    export PGPASSWORD="${DB_PASSWORD}"
    pg_dump --host="${DB_HOST}" --port="${DB_PORT}" --dbname="${DB_DATABASE}" --username="${DB_USERNAME}" --no-password | gzip > "${BACKUP_FILE}"
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

if [ "$?" != 0 ]; then
  echo "could not export database"
  exit 1
fi

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