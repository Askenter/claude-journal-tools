#!/usr/bin/env bash
# First-time per-device setup for the cognitive consolidation pipeline.
# Usage: ./scripts/init-journal-device.sh <device-name>
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${HERE}/venv/bin/python" -m tools.journal.init_device "$@"
