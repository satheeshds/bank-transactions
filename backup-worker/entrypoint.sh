#!/bin/sh

check_env() {
  if [ -z "$1" ]; then
    echo "environment variable is missing a value"
    exit 1
  fi
}

# rclone command
if [ "$1" = "rclone" ]; then
  $*
  exit 0
fi

echo "DB debug: DB_CONNECTION='${DB_CONNECTION}' DB_HOST='${DB_HOST}' DB_PORT='${DB_PORT}' DB_DATABASE='${DB_DATABASE}' DB_USERNAME='${DB_USERNAME}' DB_FILE='${DB_FILE}'"

# check if all environment variables are set
check_env "${TZ}"
check_env "${RCLONE_REMOTE}"
check_env "${BACKUP_FOLDER}"
check_env "${BACKUP_AGE}"
check_env "${DB_CONNECTION}"
if [ "${DB_CONNECTION}" = "sqlite" ]; then
  check_env "${DB_FILE}"
  [ -f "/database/${DB_FILE}" ] || { echo "sqlite database file not found: /database/${DB_FILE}"; exit 1; }
else
  check_env "${DB_HOST}"
  check_env "${DB_PORT}"
  check_env "${DB_DATABASE}"
  check_env "${DB_USERNAME}"
  check_env "${DB_PASSWORD}"
fi

# check if rclone config exists
rclone config show "${RCLONE_REMOTE}" > /dev/null
if [ "$?" != 0 ]; then
  echo "rclone config does not exist"
  exit 1
else
  echo "rclone config exists"
fi

# check if rclone config is functional
rclone mkdir "${RCLONE_REMOTE}:${BACKUP_FOLDER}" > /dev/null
if [ "$?" != 0 ]; then
  echo "rclone config is incorrect"
  exit 1
else
  echo "rclone config is correct"
fi

# configure crontab
# crontab -l | grep -q "backup.sh" && echo "cron entry exists" || echo "${CRON} cd /app/src && sh backup.sh > /dev/stdout" | crontab - && echo "created cron entry"


echo "starting fcron"
exec "$@"