#!/usr/bin/env bash
# Shared helpers for infra/gb10/*.sh. Source this file; do not run it.
# Everything installs under $STUDIO_ROOT (default /opt/studio). Nothing here touches the app code.
set -Eeuo pipefail

STUDIO_ROOT="${STUDIO_ROOT:-/opt/studio}"
STUDIO_VENVS="${STUDIO_ROOT}/venvs"
STUDIO_MODELS="${STUDIO_ROOT}/models"
STUDIO_SECRETS="${STUDIO_ROOT}/secrets"
STUDIO_TOOLS="${STUDIO_ROOT}/tools"
STUDIO_LOG_DIR="${STUDIO_ROOT}/logs"
export STUDIO_ROOT STUDIO_VENVS STUDIO_MODELS STUDIO_SECRETS STUDIO_TOOLS STUDIO_LOG_DIR

gb10_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

gb10_log() { printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*" >&2; }
gb10_die() { gb10_log "ERROR: $*"; exit 1; }
gb10_require_cmd() { command -v "$1" >/dev/null 2>&1 || gb10_die "missing command: $1"; }
gb10_require_arm64() { [[ "$(uname -m)" == "aarch64" ]] || gb10_die "expected aarch64 (GB10); got $(uname -m)"; }

# $STUDIO_ROOT is usually root-owned on first run; hand it to the current user once.
gb10_ensure_root() {
  if [[ ! -d "${STUDIO_ROOT}" ]]; then
    sudo install -d -m 755 -o "$(id -un)" -g "$(id -gn)" "${STUDIO_ROOT}"
  fi
  [[ -w "${STUDIO_ROOT}" ]] || gb10_die "${STUDIO_ROOT} is not writable by $(id -un)"
  mkdir -p "${STUDIO_VENVS}" "${STUDIO_MODELS}" "${STUDIO_TOOLS}" "${STUDIO_LOG_DIR}"
  install -d -m 700 "${STUDIO_SECRETS}"
}

# Keep every downloaded weight under $STUDIO_MODELS instead of ~/.cache.
gb10_hf_env() {
  export HF_HOME="${HF_HOME:-${STUDIO_MODELS}/hf}"
  export TORCH_HOME="${TORCH_HOME:-${STUDIO_MODELS}/torch}"
  mkdir -p "${HF_HOME}" "${TORCH_HOME}"
}

# The LTX venv is the only proven aarch64 CUDA torch on this host. New venvs pin the same
# torch version and wheel index. Override with STUDIO_TORCH_INDEX_URL / STUDIO_TORCH_SPEC.
gb10_detect_torch() {
  if [[ -n "${STUDIO_TORCH_INDEX_URL:-}" ]]; then
    TORCH_INDEX_URL="${STUDIO_TORCH_INDEX_URL}"
    TORCH_SPEC="${STUDIO_TORCH_SPEC:-torch}"
    export TORCH_INDEX_URL TORCH_SPEC
    gb10_log "torch: ${TORCH_SPEC} from ${TORCH_INDEX_URL} (override)"
    return
  fi
  if [[ -z "${LTX_PYTHON:-}" && -f "${gb10_repo_root}/.env.local" ]]; then
    LTX_PYTHON="$(grep -E '^LTX_PYTHON=' "${gb10_repo_root}/.env.local" | tail -n1 | cut -d= -f2- | tr -d '"'"'")"
  fi
  [[ -n "${LTX_PYTHON:-}" && -x "${LTX_PYTHON}" ]] \
    || gb10_die "Set LTX_PYTHON to the existing LTX venv python (or STUDIO_TORCH_INDEX_URL)"
  local info version cuda
  info="$("${LTX_PYTHON}" -c 'import torch; print(torch.__version__); print(torch.version.cuda or "")')"
  version="$(sed -n 1p <<<"${info}")"
  cuda="$(sed -n 2p <<<"${info}")"
  [[ -n "${cuda}" ]] || gb10_die "LTX torch ${version} is not a CUDA build; refusing to guess an index"
  TORCH_SPEC="torch==${version%%+*}"
  TORCH_INDEX_URL="https://download.pytorch.org/whl/cu${cuda//./}"
  export TORCH_SPEC TORCH_INDEX_URL
  gb10_log "torch: ${TORCH_SPEC} from ${TORCH_INDEX_URL} (matches LTX venv ${version})"
}

# Prints the venv path on stdout; logs go to stderr so callers can capture the path.
gb10_make_venv() {
  local path="${STUDIO_VENVS}/$1"
  if [[ ! -x "${path}/bin/python" ]]; then
    python3 -m venv "${path}" || gb10_die "python3 -m venv failed; sudo apt-get install -y python3-venv"
  fi
  "${path}/bin/pip" install --quiet --upgrade pip wheel
  printf '%s' "${path}"
}

# gb10_pip_torch VENV [extra torch-family packages...]
gb10_pip_torch() {
  local venv="$1"; shift
  "${venv}/bin/pip" install --index-url "${TORCH_INDEX_URL}" "${TORCH_SPEC}" "$@"
}
