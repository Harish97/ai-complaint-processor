"""Allow `python -m complaint_processor` as an alternative to `python run.py`."""

from complaint_processor.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
