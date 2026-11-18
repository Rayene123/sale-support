"""Normalize accents and case in catalog and request text."""

import unicodedata


def fold_text(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


COLORS = {
    "black": ("noir", "noire"), "white": ("blanc", "blanche"), "gray": ("gris", "grise", "grey"),
    "blue": ("bleu", "bleue"), "red": ("rouge",), "green": ("vert", "verte"),
    "silver": ("argent", "argente", "argentee"), "pink": ("rose",),
}
COLOR_FIELDS = {"color", "colour", "couleur"}
RAM_FIELDS = {"ram", "ram gb", "memory", "memoire", "memoire vive", "installed ram"}


def color_family(value: str) -> str | None:
    label = fold_text(value).strip()
    return next((color for color, aliases in COLORS.items()
                 if label == color or label in aliases), None)
