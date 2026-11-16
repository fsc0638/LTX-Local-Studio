#!/usr/bin/env bash
# pg_dump the studio database into data/backups/, then drop dumps older than the retention window.
# Custom format (-Fc) so a single table can be restored without replaying the whole file.
set -Eeuo pipefail

backup_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_dir="${backup_root}/data/backups"
backup_keep_days="${LTX_BACKUP_KEEP_DAYS:-14}"

if [[ -z "${LTX_DATABASE_URL:-}" ]]; then
  printf '%s\n' "LTX_DATABASE_URL is not set; refusing to guess which database to back up." >&2
  exit 1
fi

install -d -m 700 "${backup_dir}"
backup_file="${backup_dir}/ltx-studio-$(date +%Y%m%d-%H%M%S).dump"

# Write to a temporary name first: a partial file must never look like a usable backup.
/usr/bin/pg_dump --format=custom --no-owner --file="${backup_file}.partial" "${LTX_DATABASE_URL}"
mv "${backup_file}.partial" "${backup_file}"
chmod 600 "${backup_file}"

/usr/bin/find "${backup_dir}" -maxdepth 1 -name 'ltx-studio-*.dump' -type f \
  -mtime "+${backup_keep_days}" -delete

printf '%s\n' "Backed up to ${backup_file} ($(du -h "${backup_file}" | cut -f1))"
