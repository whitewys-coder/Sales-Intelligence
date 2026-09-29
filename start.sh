#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  python3 - <<'PY'
from pathlib import Path
import secrets, os
text = Path('.env.example').read_text().replace('REPLACE_WITH_RANDOM_TOKEN_AT_LEAST_24_CHARS', secrets.token_urlsafe(32))
fd = os.open('.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(text)
print('Created private .env. Copy APP_TOKEN from that file into the web login.')
PY
fi
exec python3 -m sales_agent
