FROM satheeshds/fcron-container

# install required packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    sqlite3 \
    rclone \
    gzip \
    mariadb-client \
    curl \
 && rm -rf /var/lib/apt/lists/*

# create the app directory
WORKDIR /app

# copy project folder
COPY entrypoint.sh /app/entrypoint.sh
COPY backup.sh /app/backup.sh
RUN chmod a+x /app/backup.sh
RUN chmod a+x /app/entrypoint.sh

# volume for rclone config
VOLUME ["/root/.config/rclone"]

# entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# cmd
#CMD ["anacron", "-d"]
#CMD ["anacron", "-d", "-f", "-t", "/app/anacrontab"]
# calling parent entrypoint.sh to start fcron
CMD ["/entrypoint.sh"]
