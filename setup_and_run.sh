#!/usr/bin/env bash
#
# One-command setup and demo run — macOS / Linux.
#
#   ./setup_and_run.sh
#
# Creates a virtual environment, installs the dependencies, runs the full
# pipeline against the offline provider (no API key, no network, no cost) and
# then runs the test suite.
#
# To use a real model instead, copy .env.example to .env, add your key, and run:
#   .venv/bin/python run.py

set -euo pipefail
cd "$(dirname "$0")"

echo
echo "=============================================================="
echo " AI Customer Complaint & Case Processing System — setup"
echo "=============================================================="
echo

# --- 1. Find a usable Python (3.10+) ------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PY="$candidate"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "ERROR: Python 3.10 or newer is required but was not found on PATH."
    echo "       Install it from https://www.python.org/downloads/ and re-run."
    exit 1
fi

echo "[1/4] Using $($PY --version) at $(command -v "$PY")"

# --- 2. Virtual environment ---------------------------------------------------
if [ ! -d .venv ]; then
    echo "[2/4] Creating virtual environment in .venv ..."
    "$PY" -m venv .venv
else
    echo "[2/4] Reusing existing .venv"
fi

# --- 3. Dependencies ----------------------------------------------------------
echo "[3/4] Installing dependencies (about 15 seconds) ..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt

# --- 4. Run ------------------------------------------------------------------
echo "[4/4] Running the pipeline over ./data with the offline provider ..."
echo
set +e
.venv/bin/python run.py --provider mock --log-level WARNING
RUN_EXIT=$?
set -e

echo
echo "=============================================================="
echo " Test suite"
echo "=============================================================="
.venv/bin/python -m pytest

cat <<'EOF'

==============================================================
 Done.

 Results are in  ./output
   structured_data/*.json   Task 1 — validated extraction
   customer_emails/*.txt    Task 2 — generated customer reply
   case_summaries/*.md      Task 3 — internal case note
   final_report.csv         consolidated, one row per document
   logs/run.log             full DEBUG audit trail

 Exit code 1 from the run above is expected: data/ contains two
 deliberate edge cases (an empty file and an unsupported .xlsx)
 that demonstrate error handling.

 To run against a real model:
   cp .env.example .env      # then add your OpenAI or Gemini key
   .venv/bin/python run.py

 Other options:
   .venv/bin/python run.py --help
==============================================================
EOF

exit 0
