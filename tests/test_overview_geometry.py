"""Tests for renderer-independent unfolded enclosure overview geometry."""

from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

from reportlab.pdfgen.canvas import Canvas

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.geometry import enclosure_overview_geometry, transform_overview_capsule
from pedal_drill.model import (
    CircularHole,
    DrillTemplate,
    Face,
    LineSegment,
    Point,
    Slot,
)
from pedal_drill.renderers.pdf import ReportLabPdfRenderer


def test_overview_contains_every_face_in_the_expected_net_arrangement() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    overview = enclosure_overview_geometry(enclosure)

    a = overview.face_for(Face.A).bounds
    b = overview.face_for(Face.B).bounds
    c = overview.face_for(Face.C).bounds
    d = overview.face_for(Face.D).bounds
    e = overview.face_for(Face.E).bounds

    assert {item.face for item in overview.faces} == set(Face)
    assert b.y == a.y + a.height
    assert d.y + d.height == a.y
    assert c.x + c.width == a.x
    assert e.x == a.x + a.width


def test_overview_uses_one_uniform_scale_and_fits_inside_page_margins() -> None:
    overview = enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx"),
        scale=Decimal("0.375"),
        margin=Decimal("10"),
    )

    assert {face.transform.scale for face in overview.faces} == {Decimal("0.375")}
    for face in overview.faces:
        bounds = face.bounds
        page = overview.page_bounds
        assert bounds.x >= Decimal("10")
        assert bounds.y >= Decimal("10")
        assert bounds.x + bounds.width <= page.width - Decimal("10")
        assert bounds.y + bounds.height <= page.height - Decimal("10")


def test_overview_transform_preserves_local_coordinates_and_slot_geometry() -> None:
    overview = enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx")
    )
    face = overview.face_for(Face.A)
    local_point = Point(Decimal("10"), Decimal("-20"))

    assert face.transform.point(local_point) == Point(
        face.bounds.x + (face.bounds.width / 2) + Decimal("5"),
        face.bounds.y + (face.bounds.height / 2) - Decimal("10"),
    )

    capsule = transform_overview_capsule(
        Slot(Face.A, local_point, Decimal("18"), Decimal("6"), Decimal("45")),
        face,
    )
    assert capsule.center == face.transform.point(local_point)
    assert capsule.length == Decimal("9")
    assert capsule.width == Decimal("3")
    assert capsule.angle_degrees == Decimal("45")


def test_overview_draws_features_on_matching_faces_without_calibration() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    overview = enclosure_overview_geometry(enclosure)
    template = DrillTemplate(
        holes=(CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("9")),),
        lines=(
            LineSegment(
                Face.C,
                Point(Decimal("-5"), Decimal("0")),
                Point(Decimal("5"), Decimal("0")),
            ),
        ),
        slots=(
            Slot(
                Face.D,
                Point(Decimal("0"), Decimal("0")),
                Decimal("18"),
                Decimal("6"),
                Decimal("90"),
            ),
        ),
        source_format="test",
    )
    renderer = ReportLabPdfRenderer()
    canvas = MagicMock()

    with (
        patch.object(renderer, "_draw_overview_circle") as draw_hole,
        patch.object(renderer, "_draw_overview_line") as draw_line,
        patch.object(renderer, "_draw_overview_capsule") as draw_slot,
        patch.object(renderer, "_draw_calibration_lines") as draw_calibration,
    ):
        renderer._draw_overview_page(
            cast(Canvas, canvas), template, enclosure, overview
        )

    assert draw_hole.call_args.args[3].face is Face.A
    assert draw_line.call_args.args[2].face is Face.C
    assert (
        draw_slot.call_args.args[1].center
        == overview.face_for(Face.D).transform.point(template.slots[0].center)
    )
    draw_calibration.assert_not_called()
    labels = [call.args[2] for call in canvas.drawCentredString.call_args_list]
    assert "Orientation overview - not to scale for drilling." in labels


def test_overview_highlights_only_populated_faces() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    overview = enclosure_overview_geometry(enclosure)
    template = DrillTemplate(
        holes=(CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("9")),),
        lines=(
            LineSegment(
                Face.C,
                Point(Decimal("-5"), Decimal("0")),
                Point(Decimal("5"), Decimal("0")),
            ),
        ),
        source_format="test",
    )
    renderer = ReportLabPdfRenderer()
    canvas = MagicMock()

    renderer._draw_overview_page(cast(Canvas, canvas), template, enclosure, overview)

    fill_values = [call.args[0] for call in canvas.setFillGray.call_args_list]
    assert fill_values.count(0.93) == 2
    assert fill_values.count(1.0) == 1
    metadata = [call.args[2] for call in canvas.drawString.call_args_list]
    assert "1590XX" in metadata
    assert "Outside view | 2 populated faces" in metadata
