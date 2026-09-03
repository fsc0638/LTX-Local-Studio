#!/usr/bin/env bash
# Exercise scripts/git-sync-main.sh against a throwaway origin.
#
# Builds a bare origin plus two clones under mktemp, copies the script into the "host" clone (it
# locates its repo from its own path), and drives the eight situations the script must handle.
# Every commit only touches docs-style files, so the script never writes a restart marker and
# never reaches systemctl, npm or the real services. Safe to run on the production host.
#
#   bash tests/test_git_sync.sh                 # tests the script in this checkout
#   bash tests/test_git_sync.sh /path/to/script # tests another copy
set -Eeuo pipefail

test_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
script="${1:-${test_root}/scripts/git-sync-main.sh}"
[[ -f "${script}" ]] || { echo "missing script: ${script}" >&2; exit 2; }

T="$(mktemp -d)"
trap 'rm -rf "${T}"' EXIT
G() { /usr/bin/git -c user.name=t -c user.email=t@t -c init.defaultBranch=main "$@"; }

G init -q --bare "${T}/origin.git"
G clone -q "${T}/origin.git" "${T}/host" 2>/dev/null
cd "${T}/host"
# The real repo ignores data/; the script keeps its state there and must not dirty the tree.
printf 'data/\n' >.gitignore
echo one >README.md
G add . && G commit -qm "c1" && G push -q origin main
mkdir -p scripts && cp "${script}" scripts/git-sync-main.sh
G add . && G commit -qm "c2 sync script" && G push -q origin main
G clone -q "${T}/origin.git" "${T}/other" 2>/dev/null

S="${T}/host/scripts/git-sync-main.sh"
ST="${T}/host/data/worker/git-sync"

# run EXPECTED_EXIT: runs one sync cycle, prints its last log line, fails on the wrong exit code.
run() {
  local want="$1" out rc=0
  out="$(bash "${S}" 2>&1)" || rc=$?
  echo "  exit=${rc}  $(grep -oE '\] .*' <<<"${out}" | tail -1 | cut -c3-)"
  if [[ "${rc}" != "${want}" ]]; then
    echo "  FAIL: expected exit ${want}"
    echo "${out}"
    exit 1
  fi
}
stamp() { cut -c1-7 "${ST}/deployed" 2>/dev/null || echo none; }
head7() { G rev-parse --short=7 HEAD; }
# check 'CONDITION': evaluates the string inside [[ ]] so $(stamp) and friends expand at check time.
check() { if eval "[[ $1 ]]"; then echo "  ok"; else echo "  FAIL: [[ $1 ]]"; exit 1; fi; }

echo "1. fresh host, local == origin, no stamp -> bootstraps the stamp to HEAD"
run 0
check '"$(stamp)" == "$(head7)"'

echo "2. nothing changed -> already deployed, no work"
run 0

echo "3. commit pushed from this host -> deployed even though local == origin"
echo two >NOTES.md && G add . && G commit -qm "c3 host push" && G push -q origin main
before="$(stamp)"
run 0
check '"$(stamp)" == "$(head7)" && "${before}" != "$(stamp)" && ! -f "${ST}/pending-to"'

echo "4. commit pushed from elsewhere -> fast-forward, window starts at the stamp"
( cd "${T}/other" && G pull -q --ff-only && echo three >REMOTE.md && G add . && G commit -qm "c4 remote" && G push -q origin main )
run 0
check '"$(stamp)" == "$(head7)"'

echo "5. stale pending state whose commit is an ancestor of HEAD -> window extended, not stuck"
old="$(G rev-parse HEAD~1)"
older="$(G rev-parse HEAD~2)"
echo four >MORE.md && G add . && G commit -qm "c5" && G push -q origin main
printf '%s\n' "${older}" >"${ST}/pending-from"
printf '%s\n' "${old}" >"${ST}/pending-to"
run 0
check '"$(stamp)" == "$(head7)" && ! -f "${ST}/pending-to"'

echo "6. pending commit outside HEAD's history -> refuses"
stray="$(G commit-tree -m stray "$(G rev-parse 'HEAD^{tree}')" -p "$(G rev-parse HEAD~3)")"
printf '%s\n' "${older}" >"${ST}/pending-from"
printf '%s\n' "${stray}" >"${ST}/pending-to"
run 1
rm -f "${ST}/pending-from" "${ST}/pending-to"

echo "7. deployed stamp outside HEAD's history -> refuses"
printf '%s\n' "${stray}" >"${ST}/deployed"
run 1
printf '%s\n' "$(G rev-parse HEAD)" >"${ST}/deployed"

echo "8. local commit not pushed while origin moved -> diverged, refuses"
( cd "${T}/other" && G pull -q --ff-only && echo five >R2.md && G add . && G commit -qm "c6 remote" && G push -q origin main )
echo six >LOCAL.md && G add . && G commit -qm "c7 local only"
run 1

echo
echo "ALL SCENARIOS PASSED"
