FROM debian:bookworm-slim

# install required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    anacron \
    postgresql-client \
    sqlite3 \
    tzdata \
    rclone \
    mariadb-client \
 && rm -rf /var/lib/apt/lists/*

# create the app directory
WORKDIR /app

# copy project folder
COPY entrypoint.sh /app/entrypoint.sh
COPY backup.sh /etc/cron.daily/backup.sh

# copy rclone binary
# COPY --from=rclone/rclone:latest /usr/local/bin/rclone /usr/bin/rclone

# copy mysqldump binary
# COPY --from=linuxserver/mariadb:alpine /usr/bin/mysqldump /usr/bin/mysqldump

RUN chmod +x /etc/cron.daily/backup.sh
RUN chmod +x /app/entrypoint.sh

# volume for rclone config
VOLUME ["/root/.config/rclone"]

# entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# cmd
CMD ["anacron", "-d"]