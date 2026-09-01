#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env.local"
NODE_BIN="/home/kwayrdc/.nvm/versions/node/v24.20.0/bin/node"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Configure the local service before starting it." >&2
  exit 1
fi

umask 0077
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

cd "${PROJECT_ROOT}"
/usr/bin/python3 scripts/check-service-layout.py

case "${1:-}" in
  api)
    exec /usr/bin/python3 -u local_backend.py
    ;;
  web)
    if [[ ! -f "${PROJECT_ROOT}/dist/server/index.js" ]]; then
      echo "Missing production build. Run: npm run build:cloudflare" >&2
      exit 1
    fi
    if [[ ! -x "${NODE_BIN}" ]]; then
      echo "Missing Node.js runtime: ${NODE_BIN}" >&2
      exit 1
    fi
    export NEXT_PUBLIC_LTX_API_BASE=
    export NEXT_PUBLIC_LTX_MEDIA_BASE=
    exec "${NODE_BIN}" "${PROJECT_ROOT}/node_modules/vinext/dist/cli.js" start --hostname 127.0.0.1 --port 3000
    ;;
  *)
    echo "Usage: $0 api|web" >&2
    exit 64
    ;;
esac
