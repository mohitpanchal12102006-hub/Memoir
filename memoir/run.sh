#!/usr/bin/env bash
# Starts Memoir on macOS or Linux. First run creates a private Python environment (needs internet once).
set -e
cd "$(dirname "$0")/engine"
if ! command -v python3 >/dev/null 2>&1; then echo "Python 3.10 or newer is required. Install it from python.org."; exit 1; fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q -r requirements.txt
exec python -m memoir_engine "$@"
