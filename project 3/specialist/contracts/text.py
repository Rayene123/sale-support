"""Normalize accents and case in catalog and request text."""

import unicodedata


def fold_text(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))
