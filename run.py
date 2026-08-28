#!/usr/bin/env python3
"""Entry point: `python run.py [options]`.

Adds `src/` to the import path so the project runs straight from a clone with no
`pip install -e .` step, which keeps the evaluator's setup to two commands.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from complaint_processor.cli import main  # noqa: E402  (path setup must come first)

if __name__ == "__main__":
    raise SystemExit(main())
