from decimal import Decimal

import pytest

from pedal_drill.model import CircularHole, Face, Point, Slot


def test_circular_hole_requires_positive_diameter() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("0"))


def test_slot_requires_a_width_and_length_at_least_that_width() -> None:
    with pytest.raises(ValueError, match="width"):
        Slot(
            Face.A,
            Point(Decimal("0"), Decimal("0")),
            Decimal("10"),
            Decimal("0"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="at least"):
        Slot(
            Face.A,
            Point(Decimal("0"), Decimal("0")),
            Decimal("3"),
            Decimal("4"),
            Decimal("0"),
        )
