"""Tests for renderer-independent unfolded enclosure overview geometry."""

from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from reportlab.pdfgen.canvas import Canvas

from pedal_drill.enclosures import EnclosureCatalog, TrapezoidFaceDimensions
from pedal_drill.geometry import (
    Rectangle,
    enclosure_overview_geometry,
    face_corner_radius,
    fitted_enclosure_overview_geometry,
    overview_attachment_label_placement,
    transform_overview_capsule,
)
from pedal_drill.model import (
    CircularHole,
    DrillTemplate,
    Face,
    LineSegment,
    Point,
    Slot,
)
from pedal_drill.renderers.pdf import (
    OVERVIEW_DRAWING_AREA_MM,
    OVERVIEW_PAGE_BOUNDS_MM,
    OVERVIEW_SAFETY_FACTOR,
    ReportLabPdfRenderer,
)


CAD_TAPERED_ENCLOSURES = (
    "hammond-1550b",
    "hammond-1590a",
    "hammond-1590b",
    "hammond-1590b2",
    "hammond-1590bb",
    "hammond-1590g",
    "hammond-1590x",
    "hammond-1590xx",
)


def _edge_length(start: Point, end: Point) -> Decimal:
    return ((end.x - start.x) ** 2 + (end.y - start.y) ** 2).sqrt()


def _vertices_on_axis(
    vertices: tuple[Point, ...], *, axis: str, value: Decimal
) -> tuple[Point, ...]:
    return tuple(vertex for vertex in vertices if getattr(vertex, axis) == value)


def _axis_edge_length(
    vertices: tuple[Point, ...], *, axis: str, value: Decimal
) -> Decimal:
    matching = _vertices_on_axis(vertices, axis=axis, value=value)
    assert len(matching) == 2
    return _edge_length(*matching)


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


@pytest.mark.parametrize(
    "identifier",
    [
        "hammond-1590a",
        "hammond-1590b",
        "hammond-1590bb",
        "hammond-1590x",
        "hammond-1590xx",
    ],
)
def test_fitted_overview_uses_maximum_uniform_common_paper_scale(
    identifier: str,
) -> None:
    overview = fitted_enclosure_overview_geometry(
        EnclosureCatalog.built_in().get(identifier),
        page_bounds=OVERVIEW_PAGE_BOUNDS_MM,
        drawing_area=OVERVIEW_DRAWING_AREA_MM,
        safety_factor=OVERVIEW_SAFETY_FACTOR,
    )

    expected = min(
        OVERVIEW_DRAWING_AREA_MM.width / overview.net_bounds.width,
        OVERVIEW_DRAWING_AREA_MM.height / overview.net_bounds.height,
    ) * OVERVIEW_SAFETY_FACTOR
    assert overview.page_bounds == OVERVIEW_PAGE_BOUNDS_MM
    assert overview.scale == expected
    assert {face.transform.scale for face in overview.faces} == {expected}
    assert min(face.bounds.x for face in overview.faces) >= (
        OVERVIEW_DRAWING_AREA_MM.x
    )
    assert min(face.bounds.y for face in overview.faces) >= (
        OVERVIEW_DRAWING_AREA_MM.y
    )
    assert max(face.bounds.x + face.bounds.width for face in overview.faces) <= (
        OVERVIEW_DRAWING_AREA_MM.x + OVERVIEW_DRAWING_AREA_MM.width
    )
    assert max(face.bounds.y + face.bounds.height for face in overview.faces) <= (
        OVERVIEW_DRAWING_AREA_MM.y + OVERVIEW_DRAWING_AREA_MM.height
    )


def test_overview_page_fits_a4_and_us_letter_at_full_scale() -> None:
    assert OVERVIEW_PAGE_BOUNDS_MM.width == Decimal("200")
    assert OVERVIEW_PAGE_BOUNDS_MM.height == Decimal("269")
    assert OVERVIEW_PAGE_BOUNDS_MM.width <= Decimal("210.0")
    assert OVERVIEW_PAGE_BOUNDS_MM.height <= Decimal("279.4")
    assert OVERVIEW_DRAWING_AREA_MM.width == Decimal("180")
    assert OVERVIEW_DRAWING_AREA_MM.height == Decimal("226")


def test_fitted_1590xx_overview_is_substantially_larger_than_old_scale() -> None:
    overview = fitted_enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx"),
        page_bounds=OVERVIEW_PAGE_BOUNDS_MM,
        drawing_area=OVERVIEW_DRAWING_AREA_MM,
        safety_factor=OVERVIEW_SAFETY_FACTOR,
    )

    assert overview.scale > Decimal("0.75")


def test_header_and_footer_regions_are_outside_fitted_overview() -> None:
    overview = fitted_enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx"),
        page_bounds=OVERVIEW_PAGE_BOUNDS_MM,
        drawing_area=OVERVIEW_DRAWING_AREA_MM,
        safety_factor=OVERVIEW_SAFETY_FACTOR,
    )

    net_bottom = min(face.bounds.y for face in overview.faces)
    net_top = max(face.bounds.y + face.bounds.height for face in overview.faces)
    assert net_bottom > Decimal("7")
    assert net_bottom >= OVERVIEW_DRAWING_AREA_MM.y
    assert net_top <= (
        OVERVIEW_DRAWING_AREA_MM.y + OVERVIEW_DRAWING_AREA_MM.height
    )
    assert net_top < OVERVIEW_PAGE_BOUNDS_MM.height - Decimal("11")


def test_fitted_overview_is_centered_inside_drawing_area() -> None:
    overview = fitted_enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx"),
        page_bounds=OVERVIEW_PAGE_BOUNDS_MM,
        drawing_area=OVERVIEW_DRAWING_AREA_MM,
        safety_factor=OVERVIEW_SAFETY_FACTOR,
    )
    net_left = min(face.bounds.x for face in overview.faces)
    net_right = max(face.bounds.x + face.bounds.width for face in overview.faces)
    net_bottom = min(face.bounds.y for face in overview.faces)
    net_top = max(face.bounds.y + face.bounds.height for face in overview.faces)

    assert net_left - OVERVIEW_DRAWING_AREA_MM.x == pytest.approx(
        OVERVIEW_DRAWING_AREA_MM.x + OVERVIEW_DRAWING_AREA_MM.width - net_right
    )
    assert net_bottom - OVERVIEW_DRAWING_AREA_MM.y == pytest.approx(
        OVERVIEW_DRAWING_AREA_MM.y + OVERVIEW_DRAWING_AREA_MM.height - net_top
    )


@pytest.mark.parametrize("identifier", ["hammond-1590xx", "hammond-1590a"])
@pytest.mark.parametrize("face", [Face.B, Face.D])
def test_horizontal_side_label_avoids_rounded_attachment_corners(
    identifier: str, face: Face
) -> None:
    enclosure = EnclosureCatalog.built_in().get(identifier)
    overview = fitted_enclosure_overview_geometry(
        enclosure,
        page_bounds=OVERVIEW_PAGE_BOUNDS_MM,
        drawing_area=OVERVIEW_DRAWING_AREA_MM,
        safety_factor=OVERVIEW_SAFETY_FACTOR,
    )
    overview_face = overview.face_for(face)
    label = f"Face {face.value} / {'Top' if face is Face.B else 'Bottom'}"
    metrics = ReportLabPdfRenderer()._measured_text_metrics(
        label, "Helvetica", 6.0
    )
    radius = (
        face_corner_radius(overview_face.transform.dimensions)
        * overview_face.transform.scale
    )
    placement = overview_attachment_label_placement(
        overview_face,
        text_width=metrics.width,
        text_ascent=metrics.ascent,
        text_descent=metrics.descent,
        corner_radius=radius,
    )

    assert placement.bounds.x >= placement.safe_left
    assert placement.bounds.x + placement.bounds.width <= placement.safe_right
    assert placement.anchor.x == (placement.safe_left + placement.safe_right) / 2
    assert placement.bounds.x >= overview_face.bounds.x
    assert placement.bounds.x + placement.bounds.width <= (
        overview_face.bounds.x + overview_face.bounds.width
    )
    assert placement.bounds.y >= overview_face.bounds.y
    assert placement.bounds.y + placement.bounds.height <= (
        overview_face.bounds.y + overview_face.bounds.height
    )

    face_a = overview.face_for(Face.A)
    if face is Face.B:
        attachment_y = face_a.bounds.y + face_a.bounds.height
        assert placement.bounds.y > attachment_y
    else:
        attachment_y = face_a.bounds.y
        assert placement.bounds.y + placement.bounds.height < attachment_y

    for corner in overview_face.outline.vertices:
        corner_area = Rectangle(
            corner.x - radius,
            corner.y - radius,
            radius * 2,
            radius * 2,
        )
        assert not _rectangles_overlap(placement.bounds, corner_area)


def test_attachment_label_calculation_does_not_change_overview_scale() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    overview = fitted_enclosure_overview_geometry(
        enclosure,
        page_bounds=OVERVIEW_PAGE_BOUNDS_MM,
        drawing_area=OVERVIEW_DRAWING_AREA_MM,
        safety_factor=OVERVIEW_SAFETY_FACTOR,
    )
    original_scale = overview.scale
    overview_face = overview.face_for(Face.B)
    metrics = ReportLabPdfRenderer()._measured_text_metrics(
        "Face B / Top", "Helvetica", 6.0
    )

    overview_attachment_label_placement(
        overview_face,
        text_width=metrics.width,
        text_ascent=metrics.ascent,
        text_descent=metrics.descent,
        corner_radius=(
            face_corner_radius(overview_face.transform.dimensions)
            * overview_face.transform.scale
        ),
    )

    assert overview.scale == original_scale


def test_vertical_overview_face_labels_keep_their_existing_placement() -> None:
    overview = enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx")
    )
    renderer = ReportLabPdfRenderer()
    canvas = MagicMock()

    for face in (Face.C, Face.E):
        overview_face = overview.face_for(face)
        renderer._draw_overview_face_label(cast(Canvas, canvas), overview_face)
        expected_translation = (
            renderer._points(overview_face.bounds.x + Decimal("3")),
            renderer._points(
                overview_face.bounds.y + overview_face.bounds.height / 2
            ),
        )
        assert canvas.translate.call_args_list[-1].args == expected_translation
        assert canvas.rotate.call_args_list[-1].args == (90,)


def test_rectangular_side_face_uses_the_safe_horizontal_label_placement() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590b3")
    overview = fitted_enclosure_overview_geometry(
        enclosure,
        page_bounds=OVERVIEW_PAGE_BOUNDS_MM,
        drawing_area=OVERVIEW_DRAWING_AREA_MM,
        safety_factor=OVERVIEW_SAFETY_FACTOR,
    )
    canvas = MagicMock()

    ReportLabPdfRenderer()._draw_overview_face_label(
        cast(Canvas, canvas), overview.face_for(Face.B)
    )

    canvas.drawCentredString.assert_called_once()
    canvas.drawString.assert_not_called()


def _rectangles_overlap(first: Rectangle, second: Rectangle) -> bool:
    return not (
        first.x + first.width <= second.x
        or second.x + second.width <= first.x
        or first.y + first.height <= second.y
        or second.y + second.height <= first.y
    )


def test_overview_trapezoids_taper_away_from_face_a() -> None:
    overview = enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx"),
        scale=Decimal("1"),
        margin=Decimal("10"),
    )
    a = overview.face_for(Face.A)
    b = overview.face_for(Face.B)
    c = overview.face_for(Face.C)
    d = overview.face_for(Face.D)
    e = overview.face_for(Face.E)

    assert b.outline.vertices[0].y == a.bounds.y + a.bounds.height
    assert d.outline.vertices[0].y == a.bounds.y
    assert c.outline.vertices[0].x == a.bounds.x
    assert e.outline.vertices[0].x == a.bounds.x + a.bounds.width
    assert b.outline.bounds.width == Decimal("121.20")
    assert c.outline.bounds.height == Decimal("145.20")
    assert {face.transform.scale for face in (a, b, c, d, e)} == {Decimal("1")}


def test_all_side_faces_attach_their_narrow_face_a_edge() -> None:
    overview = enclosure_overview_geometry(
        EnclosureCatalog.built_in().get("hammond-1590xx"),
        scale=Decimal("1"),
        margin=Decimal("10"),
    )
    a = overview.face_for(Face.A)
    b = overview.face_for(Face.B)
    c = overview.face_for(Face.C)
    d = overview.face_for(Face.D)
    e = overview.face_for(Face.E)

    assert b.bounds.y == a.bounds.y + a.bounds.height
    assert _axis_edge_length(
        b.outline.vertices, axis="y", value=b.bounds.y
    ) == Decimal("119.36")
    assert _axis_edge_length(
        b.outline.vertices, axis="y", value=b.bounds.y + b.bounds.height
    ) == Decimal("121.20")

    assert d.bounds.y + d.bounds.height == a.bounds.y
    assert _axis_edge_length(
        d.outline.vertices, axis="y", value=d.bounds.y + d.bounds.height
    ) == Decimal("119.36")
    assert _axis_edge_length(
        d.outline.vertices, axis="y", value=d.bounds.y
    ) == Decimal("121.20")

    assert c.bounds.x + c.bounds.width == a.bounds.x
    assert _axis_edge_length(
        c.outline.vertices, axis="x", value=c.bounds.x + c.bounds.width
    ) == Decimal("143.36")
    assert _axis_edge_length(
        c.outline.vertices, axis="x", value=c.bounds.x
    ) == Decimal("145.20")

    assert e.bounds.x == a.bounds.x + a.bounds.width
    assert _axis_edge_length(
        e.outline.vertices, axis="x", value=e.bounds.x
    ) == Decimal("143.36")
    assert _axis_edge_length(
        e.outline.vertices, axis="x", value=e.bounds.x + e.bounds.width
    ) == Decimal("145.20")


@pytest.mark.parametrize("identifier", CAD_TAPERED_ENCLOSURES)
def test_cad_tapered_overviews_attach_the_narrow_edge_to_face_a(
    identifier: str,
) -> None:
    enclosure = EnclosureCatalog.built_in().get(identifier)
    overview = enclosure_overview_geometry(
        enclosure, scale=Decimal("1"), margin=Decimal("10")
    )
    a = overview.face_for(Face.A)
    b = overview.face_for(Face.B)
    c = overview.face_for(Face.C)
    d = overview.face_for(Face.D)
    e = overview.face_for(Face.E)
    width_face = enclosure.dimensions_for(Face.B)
    length_face = enclosure.dimensions_for(Face.C)
    assert isinstance(width_face, TrapezoidFaceDimensions)
    assert isinstance(length_face, TrapezoidFaceDimensions)

    assert _axis_edge_length(
        b.outline.vertices, axis="y", value=a.bounds.y + a.bounds.height
    ) == width_face.top_width
    assert _axis_edge_length(
        b.outline.vertices, axis="y", value=b.bounds.y + b.bounds.height
    ) == width_face.bottom_width
    assert _axis_edge_length(
        d.outline.vertices, axis="y", value=a.bounds.y
    ) == width_face.top_width
    assert _axis_edge_length(
        d.outline.vertices, axis="y", value=d.bounds.y
    ) == width_face.bottom_width
    assert _axis_edge_length(
        c.outline.vertices, axis="x", value=a.bounds.x
    ) == length_face.top_width
    assert _axis_edge_length(
        c.outline.vertices, axis="x", value=c.bounds.x
    ) == length_face.bottom_width
    assert _axis_edge_length(
        e.outline.vertices, axis="x", value=a.bounds.x + a.bounds.width
    ) == length_face.top_width
    assert _axis_edge_length(
        e.outline.vertices, axis="x", value=e.bounds.x + e.bounds.width
    ) == length_face.bottom_width


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
