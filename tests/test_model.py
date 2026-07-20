from decimal import Decimal

import pytest

from pedal_drill.model import CircularHole, Face, Point


def test_circular_hole_requires_positive_diameter() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("0"))
