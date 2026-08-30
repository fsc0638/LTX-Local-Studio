#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  sleep) exec sleep 30 ;;
  broken) printf 'corrupt-output' > "$2" ;;
  *) cp "$LTX_TEST_FIXTURE" "$2" ;;
esac
