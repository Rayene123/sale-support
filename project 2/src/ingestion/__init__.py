"""Ingestion package for the Project 2 corpus.

Public entry point::

    python -m src.ingestion build

Run it from ``project 2/`` (or use ``scripts/build_corpus.py``, which sets the
path up from any directory).
"""

from .build import build_corpus
from .schema import ArticleRecord, validate_record

__all__ = ["build_corpus", "ArticleRecord", "validate_record"]
