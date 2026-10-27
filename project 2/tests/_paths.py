"""Make the ingestion package importable from the tests.

Discovery inserts the tests directory on ``sys.path``, so importing this module
is enough. It also exposes the conventional data locations used by the
integration test.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

# Real local credentials must never turn ordinary unit tests into paid/cloud runs.
os.environ.update(GENERATION_PROVIDER="ollama", RETRIEVAL_BACKEND="local", ALLOW_PAID_CALLS="false")
os.environ.update(OPENAI_BUDGET_FILE="", OPENAI_BUDGET_USD="", DEMO_PASSWORD="")
os.environ.update(CALIBRATION_FILE="", MIN_RETRIEVAL_SCORE="0", QUESTION_REWRITING="true")

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
