#!/usr/bin/env bash
# Restores a backup into a NEW database; never replaces the app database.
set -euo pipefail
cd "$(dirname "$0")/.."
backup_file="${1:?Usage: scripts/check_backup.sh backups/medkit-TIMESTAMP.dump}"
test -f "$backup_file"
check_db="medkit_restore_check_$(date -u +%Y%m%d%H%M%S)"
bash scripts/compose.sh exec -T db createdb -U medkit "$check_db"
bash scripts/compose.sh exec -T db pg_restore --no-owner --single-transaction -U medkit -d "$check_db" < "$backup_file"
query="SELECT count(*)::text || ':' || md5(string_agg(id::text || snapshot::text || items::text, '|' ORDER BY id)) FROM inspections WHERE lifecycle='COMPLETED'"
original=$(bash scripts/compose.sh exec -T db psql -U medkit -d medkit -tAc "$query")
restored=$(bash scripts/compose.sh exec -T db psql -U medkit -d "$check_db" -tAc "$query")
if [ "$original" != "$restored" ]; then
    printf 'FAIL: restored snapshot checksum differs. Retained database: %s\n' "$check_db"
    exit 1
fi
printf 'PASS: original/restored completed snapshots match (%s). Database: %s\n' "$original" "$check_db"
# Retain the verification DB for inspection; operator may drop it after review.
