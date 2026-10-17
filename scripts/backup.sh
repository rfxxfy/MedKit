#!/usr/bin/env bash
# Run once per day using the server's scheduler. Keep the last seven backups.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup_file="backups/medkit-$(date -u +%Y%m%dT%H%M%SZ).dump"
bash scripts/compose.sh exec -T db pg_dump -U medkit -d medkit -Fc > "$backup_file.partial"
mv "$backup_file.partial" "$backup_file"
# Names are generated above; do not parse user-controlled paths.
python3 - <<'PY'
from pathlib import Path
for path in sorted(Path('backups').glob('medkit-*.dump'), reverse=True)[7:]:
    path.unlink()
PY
printf 'Backup written: %s\n' "$backup_file"
