"""Length-unit normalization for data-driven enclosure definitions."""

from __future__ import annotations

from decimal import Decimal

BASE_UNIT = "mm"


def to_base_unit(value: Decimal, unit: str) -> Decimal:
    """Convert a definition value to the application's base unit.

    Millimetres are the only supported input unit today. Keeping conversion at
    the JSON-loading boundary lets future units use the same JSON shape.
    """

    if unit != BASE_UNIT:
        raise ValueError(f"Unsupported enclosure unit: {unit!r}.")
    return value
