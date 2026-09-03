#!/usr/bin/env bash
# GB10 preflight: hardware, tooling, LTX venv torch, disk. Only creates $STUDIO_ROOT directories.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

gb10_require_arm64
for cmd in python3 git curl nvidia-smi free df; do gb10_require_cmd "${cmd}"; done
python3 -c 'import sys; assert sys.version_info >= (3, 10), sys.version' || gb10_die "python3 >= 3.10 required"
python3 -c 'import ensurepip' 2>/dev/null || gb10_die "python3-venv missing: sudo apt-get install -y python3-venv"

gb10_log "GPU: $(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader)"
gb10_log "Unified memory: $(free -g | awk '/^Mem:/ {print $2 " GB total, " $7 " GB available"}')"
gb10_ensure_root
gb10_log "Disk at ${STUDIO_ROOT}: $(df -h "${STUDIO_ROOT}" | awk 'NR==2 {print $4 " free of " $2}')"
command -v ffmpeg >/dev/null 2>&1 || gb10_log "WARN: ffmpeg missing (30-audio.sh installs it)"
gb10_detect_torch
gb10_log "Preflight OK. Layout: ${STUDIO_ROOT}/{venvs,models,secrets,tools,logs}"
