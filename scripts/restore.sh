#!/usr/bin/env bash
# Explicit operator command: replaces the current DB contents using a backup.
set -euo pipefail
cd "$(dirname "$0")/.."
backup_file="${1:?Usage: scripts/restore.sh backups/medkit-TIMESTAMP.dump}"
test -f "$backup_file"
bash scripts/compose.sh stop app
bash scripts/compose.sh exec -T db pg_restore --clean --if-exists --no-owner --single-transaction -U medkit -d medkit < "$backup_file"
bash scripts/compose.sh start app
curl --retry 15 --retry-delay 2 --retry-all-errors -fsS http://localhost:8010/health/ready
