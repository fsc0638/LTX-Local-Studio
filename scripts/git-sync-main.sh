#!/usr/bin/env bash
set -Eeuo pipefail

sync_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sync_state_dir="${sync_root}/data/worker/git-sync"
sync_python="${LTX_SYNC_PYTHON:-/usr/bin/python3}"
sync_node="${LTX_SYNC_NODE:-/usr/bin/node}"
sync_npm="${LTX_SYNC_NPM:-/usr/bin/npm}"

mkdir -p "${sync_state_dir}"
chmod 0700 "${sync_state_dir}"
exec 9>"${sync_state_dir}/lock"
if ! /usr/bin/flock -n 9; then
  printf '%s\n' "LTX git sync is already running; skipping this cycle."
  exit 0
fi

cd "${sync_root}"

sync_log() {
  printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
}

sync_commit_from_file() {
  local sync_file="$1" sync_value
  sync_value="$(<"${sync_file}")"
  if [[ ! "${sync_value}" =~ ^[0-9a-f]{40}$ ]]; then
    sync_log "Invalid sync state in ${sync_file}; refusing to continue." >&2
    return 1
  fi
  printf '%s' "${sync_value}"
}

# The commit whose UI build and services are live. Written after every completed cycle; a host
# that was deployed by hand before the stamp existed bootstraps to HEAD. Fails when the stamp is
# not an ancestor of HEAD, which means main was reset or rebased underneath the deployment.
sync_deployed_commit() {
  local sync_head="$1" sync_file="${sync_state_dir}/deployed" sync_value
  if [[ ! -f "${sync_file}" ]]; then
    printf '%s\n' "${sync_head}" >"${sync_file}"
    sync_log "No deployed-commit stamp; recording ${sync_head:0:7} as currently deployed." >&2
    printf '%s' "${sync_head}"
    return 0
  fi
  sync_value="$(sync_commit_from_file "${sync_file}")" || return 1
  if ! /usr/bin/git merge-base --is-ancestor "${sync_value}" "${sync_head}"; then
    sync_log "Deployed commit ${sync_value:0:7} is not an ancestor of HEAD; manual review is required." >&2
    return 1
  fi
  printf '%s' "${sync_value}"
}

sync_active_jobs() {
  /usr/bin/sqlite3 -readonly data/worker/jobs.sqlite3 \
    "SELECT count(*) FROM jobs WHERE json_extract(snapshot,'$.status') IN ('queued','running');"
}

sync_wait_active() {
  local sync_unit="$1"
  for _ in {1..20}; do
    if /usr/bin/systemctl --user is-active --quiet "${sync_unit}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

sync_wait_http() {
  local sync_url="$1" sync_expected="$2" sync_code
  for _ in {1..30}; do
    sync_code="$(/usr/bin/curl -sS -o /dev/null -w '%{http_code}' "${sync_url}" || true)"
    if [[ "${sync_code}" == "${sync_expected}" ]]; then
      return 0
    fi
    sleep 1
  done
  sync_log "Health check failed for ${sync_url}."
  return 1
}

sync_apply_restarts() {
  if [[ -f "${sync_state_dir}/restart-web" ]]; then
    sync_log "Restarting ltx-web.service after a verified UI build."
    /usr/bin/systemctl --user restart ltx-web.service
    sync_wait_active ltx-web.service
    sync_wait_http http://127.0.0.1:3000/ 200
    rm -f "${sync_state_dir}/restart-web"
  fi

  if [[ -f "${sync_state_dir}/restart-api" ]]; then
    local sync_jobs
    sync_jobs="$(sync_active_jobs)"
    if [[ "${sync_jobs}" != "0" ]]; then
      sync_log "Deferring ltx-api.service restart; ${sync_jobs} generation job(s) are active."
      return 0
    fi
    sync_log "Restarting ltx-api.service after verified backend tests."
    /usr/bin/systemctl --user restart ltx-api.service
    sync_wait_active ltx-api.service
    sync_wait_http http://127.0.0.1:8787/api/auth/config 200
    rm -f "${sync_state_dir}/restart-api"
  fi
}

sync_branch="$(/usr/bin/git symbolic-ref --quiet --short HEAD || true)"
if [[ "${sync_branch}" != "main" ]]; then
  sync_log "Refusing automatic sync outside the main branch (current: ${sync_branch:-detached})."
  exit 1
fi
if [[ -n "$(/usr/bin/git status --porcelain)" ]]; then
  sync_log "Refusing automatic sync because the working tree is not clean."
  exit 1
fi

sync_apply_restarts

sync_pending_from="${sync_state_dir}/pending-from"
sync_pending_to="${sync_state_dir}/pending-to"
sync_head="$(/usr/bin/git rev-parse HEAD)"
if [[ -f "${sync_pending_from}" || -f "${sync_pending_to}" ]]; then
  [[ -f "${sync_pending_from}" && -f "${sync_pending_to}" ]] || {
    sync_log "Incomplete pending-validation state; refusing to continue."
    exit 1
  }
  sync_from="$(sync_commit_from_file "${sync_pending_from}")"
  sync_to="$(sync_commit_from_file "${sync_pending_to}")"
  if [[ "${sync_head}" != "${sync_to}" ]]; then
    # A cycle that died mid-validation must not pin the host to that commit forever. When main has
    # simply moved forward since, widen the window to HEAD and validate everything from the last
    # deployed commit. A reset or rebase still needs a person.
    if ! /usr/bin/git merge-base --is-ancestor "${sync_to}" "${sync_head}"; then
      sync_log "HEAD moved off the pending commit ${sync_to:0:7} (now ${sync_head:0:7}); manual review is required."
      exit 1
    fi
    sync_log "HEAD advanced from ${sync_to:0:7} to ${sync_head:0:7} while validation was pending; extending the window."
    sync_to="${sync_head}"
    printf '%s\n' "${sync_to}" >"${sync_pending_to}"
  fi
else
  /usr/bin/git fetch --prune origin main
  sync_remote="$(/usr/bin/git rev-parse origin/main)"
  # Validate from the last deployed commit, not from HEAD. Commits pushed from this host move HEAD
  # without going through a deploy; a window that starts at HEAD would never build them.
  sync_from="$(sync_deployed_commit "${sync_head}")"
  if [[ "${sync_remote}" == "${sync_head}" ]]; then
    if [[ "${sync_from}" == "${sync_head}" ]]; then
      sync_log "origin/main is already synchronized and ${sync_head:0:7} is deployed."
      exit 0
    fi
    sync_to="${sync_head}"
    printf '%s\n' "${sync_from}" >"${sync_pending_from}"
    printf '%s\n' "${sync_to}" >"${sync_pending_to}"
    sync_log "Deploying ${sync_from:0:7}..${sync_to:0:7}, which reached main from this host."
  else
    if ! /usr/bin/git merge-base --is-ancestor "${sync_head}" "${sync_remote}"; then
      sync_log "Local main and origin/main have diverged; automatic merge is disabled."
      exit 1
    fi
    sync_to="${sync_remote}"
    printf '%s\n' "${sync_from}" >"${sync_pending_from}"
    printf '%s\n' "${sync_to}" >"${sync_pending_to}"
    /usr/bin/git merge --ff-only "${sync_to}"
    sync_log "Fast-forwarded main from ${sync_head:0:7} to ${sync_to:0:7}."
  fi
fi

sync_changes="$(/usr/bin/git diff --name-only "${sync_from}..${sync_to}")"
if grep -Eq '^(package.json|package-lock.json|\.nvmrc)$' <<<"${sync_changes}"; then
  sync_log "Dependency metadata changed; automatic dependency installation and deployment are disabled."
  exit 1
fi

/usr/bin/git diff --check "${sync_from}..${sync_to}"

sync_web=0
sync_backend=0
sync_js_tests=0
sync_python_tests=0
if grep -Eq '^(app/|components/|hooks/|lib/|public/|next\.config\.|vite\.config\.|tsconfig\.json|components\.json|\.ox)' <<<"${sync_changes}"; then
  sync_web=1
fi
if grep -Eq '(^|/)tests/.*\.(mjs|js|ts|tsx)$' <<<"${sync_changes}" || [[ "${sync_web}" == "1" ]]; then
  sync_js_tests=1
fi
sync_runtime_changes="$(grep -Ev '^scripts/git-sync-main\.sh$' <<<"${sync_changes}" || true)"
if grep -Eq '(^[^/]+\.py$|^scripts/.*\.(py|sh)$|^local_adapters/)' <<<"${sync_runtime_changes}"; then
  sync_backend=1
fi
if grep -Eq '(^|/)tests/.*\.py$' <<<"${sync_changes}" || [[ "${sync_backend}" == "1" ]]; then
  sync_python_tests=1
fi

if [[ "${sync_js_tests}" == "1" ]]; then
  "${sync_node}" --test tests/studio-controls.test.mjs
fi
if [[ "${sync_python_tests}" == "1" ]]; then
  PYTHONPATH=tests "${sync_python}" -m unittest discover -s tests -p 'test_*.py'
fi
if [[ "${sync_web}" == "1" ]]; then
  "${sync_npm}" run build:cloudflare
  printf '%s\n' "${sync_to}" >"${sync_state_dir}/restart-web"
fi
if [[ "${sync_backend}" == "1" ]]; then
  printf '%s\n' "${sync_to}" >"${sync_state_dir}/restart-api"
fi

rm -f "${sync_pending_from}" "${sync_pending_to}"
printf '%s\n' "${sync_to}" >"${sync_state_dir}/deployed"
sync_log "Validation passed for ${sync_to:0:7}; applying required service restarts."
sync_apply_restarts
sync_log "Automatic sync cycle completed successfully."
