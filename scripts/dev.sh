#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
api_pid=""

cleanup() {
    if [[ -n "$api_pid" ]]; then
        kill "$api_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

cd "$project_root"
if [[ -f .env.local ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env.local
    set +a
fi

python3 scripts/check-service-layout.py
python3 local_backend.py &
api_pid=$!

echo "LTX Local Studio: http://localhost:3000"
echo "Local inference API: http://127.0.0.1:${LTX_API_PORT:-8787}"
npm run dev:web
