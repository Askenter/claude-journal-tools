#!/usr/bin/env bash
# First-time per-device setup for the cognitive consolidation pipeline.
# Usage: ./scripts/init-journal-device.sh <device-name>
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${HERE}/venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
exec env PYTHONPATH="${HERE}${PYTHONPATH:+:$PYTHONPATH}" "$PY" -m tools.journal.init_device "$@"
