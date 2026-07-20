"""Regression tests for normalized reduced-scale overview features."""

from decimal import Decimal
from pathlib import Path

from pedal_drill.model import (
    CircularHole,
    DrillTemplate,
    Face,
    LineSegment,
    Point,
    Slot,
)
from pedal_drill.overview import (
    OverviewCapsule,
    OverviewCircle,
    OverviewCompoundOutline,
    OverviewLine,
    overview_features,
)
from pedal_drill.parsers import TaydaTxtParser


def test_tayda_compound_holes_and_lines_merge_into_one_source_outline() -> None:
    template = TaydaTxtParser().parse_file(
        Path(__file__).parent / "data" / "tayda_compound_capsule.txt"
    )

    features = overview_features(template, Face.A)

    compounds = [
        feature for feature in features if isinstance(feature, OverviewCompoundOutline)
    ]
    circles = [feature for feature in features if isinstance(feature, OverviewCircle)]
    lines = [feature for feature in features if isinstance(feature, OverviewLine)]
    assert len(compounds) == 1
    assert len(circles) == 1
    assert len(lines) == 1

    compound = compounds[0]
    assert compound.source_first_side == OverviewLine(
        Point(Decimal("-18.369"), Decimal("10.17")),
        Point(Decimal("-26.838"), Decimal("27.157")),
    )
    assert compound.source_second_side == OverviewLine(
        Point(Decimal("-15.684"), Decimal("11.509")),
        Point(Decimal("-24.153"), Decimal("28.495")),
    )
    assert compound.first_end_arc.radius == Decimal("1.5")
    assert compound.second_end_arc.radius == Decimal("1.5")
    assert compound.is_closed
    assert compound.first_end_arc.sweep_degrees != Decimal("180")
    assert compound.second_end_arc.sweep_degrees != Decimal("180")
    assert circles[0].center == Point(Decimal("20.0"), Decimal("20.0"))
    assert lines[0] == OverviewLine(
        Point(Decimal("0"), Decimal("0")),
        Point(Decimal("5"), Decimal("0")),
    )


def test_standalone_slots_remain_overview_capsules() -> None:
    template = DrillTemplate(
        holes=(),
        slots=(
            Slot(
                Face.A,
                Point(Decimal("2"), Decimal("3")),
                Decimal("18"),
                Decimal("6"),
                Decimal("45"),
            ),
        ),
        source_format="test",
    )

    features = overview_features(template, Face.A)

    assert len(features) == 1
    assert isinstance(features[0], OverviewCapsule)
    assert features[0].capsule.length == Decimal("18")
    assert features[0].capsule.angle_degrees == Decimal("45")


def test_compound_normalization_is_independent_of_source_order_and_rotation() -> None:
    source = TaydaTxtParser().parse_file(
        Path(__file__).parent / "data" / "tayda_compound_capsule.txt"
    )
    compound_holes = source.holes[:2]
    compound_lines = source.lines[:2]
    variants = (
        (compound_holes, compound_lines),
        (tuple(reversed(compound_holes)), tuple(reversed(compound_lines))),
        (
            compound_holes,
            tuple(LineSegment(Face.A, line.end, line.start) for line in compound_lines),
        ),
        (
            tuple(_mirror_hole(hole) for hole in compound_holes),
            tuple(_mirror_line(line) for line in compound_lines),
        ),
    )

    for holes, lines in variants:
        features = overview_features(
            DrillTemplate(holes=holes, lines=lines, source_format="test"),
            Face.A,
        )
        assert len(features) == 1
        assert isinstance(features[0], OverviewCompoundOutline)
        outline = features[0]
        assert outline.is_closed
        assert outline.first_side.end == outline.second_end_arc.start
        assert outline.second_side.start == outline.first_end_arc.start
        assert outline.first_end_arc.sweep_degrees != Decimal("0")
        assert outline.second_end_arc.sweep_degrees != Decimal("0")


def _mirror_hole(hole: CircularHole) -> CircularHole:
    return CircularHole(hole.face, Point(hole.center.x, -hole.center.y), hole.diameter)


def _mirror_line(line: LineSegment) -> LineSegment:
    return LineSegment(
        line.face,
        Point(line.start.x, -line.start.y),
        Point(line.end.x, -line.end.y),
    )
