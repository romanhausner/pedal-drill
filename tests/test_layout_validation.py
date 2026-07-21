from decimal import Decimal

import pytest

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.enclosures.model import (
    EnclosureDefinition,
    FaceDimensions,
    TrapezoidFaceDimensions,
)
from pedal_drill.enclosures.validation import (
    DrillLayoutOutsideEnclosureError,
    validate_template_fits_enclosure,
)
from pedal_drill.geometry import face_polygon
from pedal_drill.model import (
    CircularHole,
    DrillTemplate,
    Face,
    LineSegment,
    Point,
    Slot,
)


@pytest.fixture
def enclosure() -> EnclosureDefinition:
    return EnclosureCatalog.built_in().get("hammond-1590b")


def _template(
    *,
    hole: CircularHole | None = None,
    slot: Slot | None = None,
    line: LineSegment | None = None,
) -> DrillTemplate:
    return DrillTemplate(
        holes=(hole,) if hole else (),
        slots=(slot,) if slot else (),
        lines=(line,) if line else (),
        source_format="test",
    )


@pytest.fixture
def trapezoid_enclosure() -> EnclosureDefinition:
    rectangle = FaceDimensions(Decimal("100"), Decimal("100"))
    trapezoid = TrapezoidFaceDimensions(
        Decimal("80"), Decimal("100"), Decimal("40")
    )
    return EnclosureDefinition(
        identifier="test-trapezoid",
        manufacturer="Test",
        model="Test",
        faces={
            Face.A: rectangle,
            Face.B: trapezoid,
            Face.C: rectangle,
            Face.D: trapezoid,
            Face.E: rectangle,
        },
        unit="mm",
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


def test_circle_fully_inside_trapezoid_is_valid(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    hole = CircularHole(Face.B, Point(Decimal("0"), Decimal("0")), Decimal("10"))

    validate_template_fits_enclosure(_template(hole=hole), trapezoid_enclosure)


def test_circle_tangent_to_sloped_edge_is_valid(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    edge_length = Decimal("1700").sqrt()
    radius = Decimal("5")
    center = Point(
        Decimal("45") - radius * Decimal("40") / edge_length,
        -radius * Decimal("10") / edge_length,
    )
    hole = CircularHole(Face.B, center, radius * 2)

    validate_template_fits_enclosure(_template(hole=hole), trapezoid_enclosure)


def test_circle_crossing_sloped_edge_is_rejected(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    hole = CircularHole(
        Face.B,
        Point(Decimal("44"), Decimal("19")),
        Decimal("2"),
    )

    with pytest.raises(DrillLayoutOutsideEnclosureError, match="right"):
        validate_template_fits_enclosure(_template(hole=hole), trapezoid_enclosure)


@pytest.mark.parametrize(
    ("face", "expected_boundary"),
    [
        (Face.B, "top"),
        (Face.C, "right"),
        (Face.D, "top"),
        (Face.E, "left"),
    ],
)
def test_trapezoid_boundary_names_follow_transformed_edge_direction(
    face: Face, expected_boundary: str
) -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    outline = face_polygon(enclosure.dimensions_for(face), face)
    start, end = outline.edges[0]
    edge_midpoint = Point((start.x + end.x) / 2, (start.y + end.y) / 2)
    hole = CircularHole(face, edge_midpoint, Decimal("1"))

    with pytest.raises(DrillLayoutOutsideEnclosureError) as caught:
        validate_template_fits_enclosure(_template(hole=hole), enclosure)

    assert caught.value.exceeded_boundaries == (expected_boundary,)


def test_rotated_trapezoids_do_not_reuse_untransformed_edge_labels() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")

    reported: dict[Face, tuple[str, ...]] = {}
    for face in (Face.C, Face.E):
        outline = face_polygon(enclosure.dimensions_for(face), face)
        start, end = outline.edges[0]
        midpoint = Point((start.x + end.x) / 2, (start.y + end.y) / 2)
        with pytest.raises(DrillLayoutOutsideEnclosureError) as caught:
            validate_template_fits_enclosure(
                _template(hole=CircularHole(face, midpoint, Decimal("1"))),
                enclosure,
            )
        reported[face] = caught.value.exceeded_boundaries

    assert reported == {Face.C: ("right",), Face.E: ("left",)}


def test_feature_inside_rectangular_bounds_can_fail_trapezoid_outline(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    hole = CircularHole(
        Face.B,
        Point(Decimal("44"), Decimal("19")),
        Decimal("1"),
    )
    assert hole.center.x + hole.diameter / 2 <= Decimal("50")
    assert hole.center.y + hole.diameter / 2 <= Decimal("20")

    with pytest.raises(DrillLayoutOutsideEnclosureError):
        validate_template_fits_enclosure(_template(hole=hole), trapezoid_enclosure)


def test_slot_fully_inside_trapezoid_is_valid(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    slot = Slot(
        Face.B,
        Point(Decimal("0"), Decimal("0")),
        Decimal("20"),
        Decimal("6"),
        Decimal("25"),
    )

    validate_template_fits_enclosure(_template(slot=slot), trapezoid_enclosure)


def test_slot_crossing_sloped_edge_is_rejected(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    slot = Slot(
        Face.B,
        Point(Decimal("38"), Decimal("10")),
        Decimal("10"),
        Decimal("6"),
        Decimal("0"),
    )

    with pytest.raises(DrillLayoutOutsideEnclosureError, match="rounded slot"):
        validate_template_fits_enclosure(_template(slot=slot), trapezoid_enclosure)


def test_line_inside_trapezoid_is_valid(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    line = LineSegment(
        Face.B,
        Point(Decimal("-20"), Decimal("0")),
        Point(Decimal("20"), Decimal("0")),
    )

    validate_template_fits_enclosure(_template(line=line), trapezoid_enclosure)


def test_line_crossing_trapezoid_outline_is_rejected(
    trapezoid_enclosure: EnclosureDefinition,
) -> None:
    line = LineSegment(
        Face.B,
        Point(Decimal("0"), Decimal("19")),
        Point(Decimal("45"), Decimal("19")),
    )

    with pytest.raises(DrillLayoutOutsideEnclosureError, match="construction line"):
        validate_template_fits_enclosure(_template(line=line), trapezoid_enclosure)


def test_rectangular_face_keeps_axis_aligned_validation() -> None:
    rectangle = EnclosureCatalog.built_in().get("hammond-1590b")
    hole = CircularHole(
        Face.A,
        Point(Decimal("25.25"), Decimal("51.20")),
        Decimal("0.001"),
    )

    validate_template_fits_enclosure(_template(hole=hole), rectangle)
