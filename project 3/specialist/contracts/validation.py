"""Validation shared by runtime inputs and sandbox tools."""

import re

from pydantic import BaseModel, ConfigDict


class StrictSchema(BaseModel):
    """Base schema that rejects unexpected fields."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


def validate_identifier(value: str) -> str:
    """Validate a bounded database identifier."""

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("Invalid identifier format.")

    return value
