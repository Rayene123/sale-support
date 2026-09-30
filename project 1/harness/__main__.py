"""Entry point so the harness can run as ``python -m harness``."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
