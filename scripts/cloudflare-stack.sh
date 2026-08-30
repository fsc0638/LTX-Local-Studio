#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env.local"
TUNNEL_CONFIG="${CLOUDFLARED_CONFIG:-${PROJECT_ROOT}/infra/cloudflare/config.yml}"
CLOUDFLARED_BIN="${CLOUDFLARED_BIN:-cloudflared}"

if ! command -v "${CLOUDFLARED_BIN}" >/dev/null 2>&1; then
  if [[ -x "${PROJECT_ROOT}/.tools/cloudflared" ]]; then
    CLOUDFLARED_BIN="${PROJECT_ROOT}/.tools/cloudflared"
  else
    echo "cloudflared is not installed. Follow docs/CLOUDFLARE.md first." >&2
    exit 1
  fi
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.example and configure the local model paths." >&2
  exit 1
fi

if [[ ! -f "${TUNNEL_CONFIG}" ]]; then
  echo "Missing ${TUNNEL_CONFIG}. Copy infra/cloudflare/config.yml.example and fill in the tunnel values." >&2
  exit 1
fi

if [[ ! -f "${PROJECT_ROOT}/dist/server/index.js" ]]; then
  echo "Missing production build. Run: npm run build:cloudflare" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

cd "${PROJECT_ROOT}"
python3 scripts/check-service-layout.py

children=()
cleanup() {
  local child
  for child in "${children[@]:-}"; do
    kill "${child}" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python3 local_backend.py &
children+=("$!")

NEXT_PUBLIC_LTX_API_BASE= NEXT_PUBLIC_LTX_MEDIA_BASE= npm run start:web &
children+=("$!")

"${CLOUDFLARED_BIN}" tunnel --config "${TUNNEL_CONFIG}" run
