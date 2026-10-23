#!/bin/sh
# Резервная копия базы раз в BACKUP_INTERVAL_S секунд (по умолчанию 2 часа — это и есть RPO),
# хранятся последние BACKUP_KEEP копий (по умолчанию 24, то есть двое суток). Запускается сервисом backup
# в docker-compose.yml; копии — в ./backups (в git не попадают). Восстановление — README, «Резервные копии».
set -eu
mkdir -p /backups
while true; do
  file="/backups/compass_$(date -u +%Y-%m-%d_%H-%M-%S).dump"
  if pg_dump -Fc -f "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup: $file, $(du -h "$file" | cut -f1)"
  else
    rm -f "$file.tmp"
    echo "backup: pg_dump завершился с ошибкой" >&2
  fi
  ls -1t /backups/compass_*.dump 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | xargs -r rm -f
  sleep "$BACKUP_INTERVAL_S"
done
