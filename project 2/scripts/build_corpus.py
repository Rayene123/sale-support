"""Build the corpus from any working directory.

``python -m src.ingestion`` requires the current directory to be ``project 2/``.
This wrapper puts ``project 2/src`` on ``sys.path`` so the same command works
from the repository root, which is how the team usually runs things:

    python "project 2/scripts/build_corpus.py"
    python "project 2/scripts/build_corpus.py" --no-download
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ingestion.cli import main  # noqa: E402  (path set up above)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["build"]))
