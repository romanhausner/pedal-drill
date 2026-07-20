from decimal import Decimal

import pytest

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.enclosures.model import EnclosureDefinition
from pedal_drill.enclosures.validation import (
    DrillLayoutOutsideEnclosureError,
    validate_template_fits_enclosure,
)
from pedal_drill.model import CircularHole, DrillTemplate, Face, Point, Slot


@pytest.fixture
def enclosure() -> EnclosureDefinition:
    return EnclosureCatalog.built_in().get("hammond-1590b")


def _template(
    *, hole: CircularHole | None = None, slot: Slot | None = None
) -> DrillTemplate:
    return DrillTemplate(
        holes=(hole,) if hole else (),
        slots=(slot,) if slot else (),
        source_format="test",
    )


def test_circle_fully_inside_is_valid(enclosure: EnclosureDefinition) -> None:
    hole = CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("10"))

    validate_template_fits_enclosure(_template(hole=hole), enclosure)


def test_circle_tangent_to_an_edge_is_valid(enclosure: EnclosureDefinition) -> None:
    hole = CircularHole(
        Face.A,
        Point(Decimal("-25.25"), Decimal("0")),
        Decimal("10"),
    )

    validate_template_fits_enclosure(_template(hole=hole), enclosure)


@pytest.mark.parametrize(
    ("center", "boundary"),
    [
        (Point(Decimal("-25.251"), Decimal("0")), "left"),
        (Point(Decimal("25.251"), Decimal("0")), "right"),
        (Point(Decimal("0"), Decimal("-51.201")), "bottom"),
        (Point(Decimal("0"), Decimal("51.201")), "top"),
    ],
)
def test_circle_crossing_each_edge_is_rejected(
    enclosure: EnclosureDefinition, center: Point, boundary: str
) -> None:
    hole = CircularHole(Face.A, center, Decimal("10"))

    with pytest.raises(DrillLayoutOutsideEnclosureError, match=boundary):
        validate_template_fits_enclosure(_template(hole=hole), enclosure)


def test_circle_completely_outside_is_rejected(
    enclosure: EnclosureDefinition,
) -> None:
    hole = CircularHole(Face.A, Point(Decimal("100"), Decimal("0")), Decimal("10"))

    with pytest.raises(DrillLayoutOutsideEnclosureError, match="circular hole"):
        validate_template_fits_enclosure(_template(hole=hole), enclosure)


def test_rounded_slot_fully_inside_is_valid(enclosure: EnclosureDefinition) -> None:
    slot = Slot(
        Face.A,
        Point(Decimal("0"), Decimal("0")),
        Decimal("20"),
        Decimal("6"),
        Decimal("30"),
    )

    validate_template_fits_enclosure(_template(slot=slot), enclosure)


def test_rounded_slot_crossing_an_edge_is_rejected(
    enclosure: EnclosureDefinition,
) -> None:
    slot = Slot(
        Face.A,
        Point(Decimal("28"), Decimal("0")),
        Decimal("20"),
        Decimal("6"),
        Decimal("45"),
    )

    with pytest.raises(DrillLayoutOutsideEnclosureError, match="rounded slot"):
        validate_template_fits_enclosure(_template(slot=slot), enclosure)
