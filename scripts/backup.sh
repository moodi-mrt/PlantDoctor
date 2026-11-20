#!/usr/bin/env bash
# Nightly backup: PostgreSQL dump + private image store. Keep 14 days locally; copy offsite with rclone/aws.
#   0 2 * * * /opt/plantdoctor/scripts/backup.sh >> /var/log/plantdoctor-backup.log 2>&1
# Restore: gunzip -c db-<stamp>.sql.gz | docker compose exec -T db psql -U plantdoctor plantdoctor
#          tar -xzf uploads-<stamp>.tgz -C <data volume>
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=${BACKUP_DIR:-./backups}; STAMP=$(date +%Y%m%d-%H%M); mkdir -p "$DEST"
docker compose exec -T db pg_dump -U plantdoctor --no-owner plantdoctor | gzip > "$DEST/db-$STAMP.sql.gz"
docker compose exec -T app tar -C /data -czf - uploads > "$DEST/uploads-$STAMP.tgz"
find "$DEST" -name '*.gz' -mtime +14 -delete; find "$DEST" -name '*.tgz' -mtime +14 -delete
echo "backup ok: $STAMP"
