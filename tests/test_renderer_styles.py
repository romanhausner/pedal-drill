"""Tests for scale-appropriate PDF drawing styles."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast

from reportlab.pdfgen.canvas import Canvas

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.geometry import (
    enclosure_overview_geometry,
    transform_overview_capsule,
)
from pedal_drill.model import CircularHole, Face, LineSegment, Point, Slot
from pedal_drill.overview import OverviewCompoundOutline, overview_features
from pedal_drill.parsers import TaydaTxtParser
from pedal_drill.renderers.pdf import ReportLabPdfRenderer
from pedal_drill.renderers.styles import (
    DETAIL_DRAWING_STYLE,
    OVERVIEW_DRAWING_STYLE,
)


class _StrokeCanvas:
    def __init__(self) -> None:
        self.line_widths: list[float] = []
        self.circle_count = 0
        self.line_count = 0
        self.centered_strings: list[str] = []
        self.paths: list[_RecordedPath] = []
        self.rotations: list[float] = []
        self.fill_grays: list[float] = []
        self.circle_options: list[dict[str, int]] = []
        self.path_options: list[dict[str, int]] = []

    def setLineWidth(self, width: float) -> None:  # noqa: N802
        self.line_widths.append(width)

    def circle(self, *_: float, **options: int) -> None:
        self.circle_count += 1
        self.circle_options.append(options)

    def line(self, *_: float) -> None:
        self.line_count += 1

    def roundRect(self, *_: float, **__: int) -> None:  # noqa: N802
        pass

    def saveState(self) -> None:  # noqa: N802
        pass

    def restoreState(self) -> None:  # noqa: N802
        pass

    def translate(self, *_: float) -> None:
        pass

    def rotate(self, _: float) -> None:
        self.rotations.append(_)

    def setFont(self, _: str, __: float) -> None:  # noqa: N802
        pass

    def setFillGray(self, value: float) -> None:  # noqa: N802
        self.fill_grays.append(value)

    def drawCentredString(self, *_: float | str) -> None:  # noqa: N802
        self.centered_strings.append(str(_[-1]))

    def beginPath(self) -> "_RecordedPath":  # noqa: N802
        path = _RecordedPath()
        self.paths.append(path)
        return path

    def drawPath(self, _: "_RecordedPath", **options: int) -> None:  # noqa: N802
        self.path_options.append(options)


class _RecordedPath:
    def __init__(self) -> None:
        self.operations: list[str] = []

    def moveTo(self, *_: float) -> None:  # noqa: N802
        self.operations.append("move")

    def lineTo(self, *_: float) -> None:  # noqa: N802
        self.operations.append("line")

    def arc(self, *_: float) -> None:
        self.operations.append("arc")

    def close(self) -> None:
        self.operations.append("close")


def test_overview_features_use_the_lighter_overview_style() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    overview_face = enclosure_overview_geometry(enclosure).face_for(Face.A)
    canvas = _StrokeCanvas()
    renderer = ReportLabPdfRenderer()

    renderer._draw_overview_hole(
        cast(Canvas, canvas),
        CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("9")),
        overview_face,
    )
    renderer._draw_overview_line(
        cast(Canvas, canvas),
        LineSegment(
            Face.A,
            Point(Decimal("-5"), Decimal("0")),
            Point(Decimal("5"), Decimal("0")),
        ),
        overview_face,
    )
    renderer._draw_overview_capsule(
        cast(Canvas, canvas),
        transform_overview_capsule(
            Slot(
                Face.A,
                Point(Decimal("0"), Decimal("0")),
                Decimal("18"),
                Decimal("6"),
                Decimal("45"),
            ),
            overview_face,
        ),
        OVERVIEW_DRAWING_STYLE,
    )

    assert canvas.line_widths == [
        OVERVIEW_DRAWING_STYLE.feature_stroke_width,
        OVERVIEW_DRAWING_STYLE.construction_line_stroke_width,
        OVERVIEW_DRAWING_STYLE.feature_stroke_width,
    ]
    assert canvas.circle_count == 1
    assert canvas.circle_options == [{"stroke": 1, "fill": 1}]
    assert canvas.line_count == 1
    assert canvas.fill_grays == [1.0, 1.0]
    assert canvas.centered_strings == []
    assert canvas.paths[0].operations == [
        "move",
        "line",
        "arc",
        "line",
        "arc",
        "close",
    ]
    assert canvas.rotations == [45.0]
    assert canvas.path_options == [{"stroke": 1, "fill": 1}]


def test_detail_features_retain_the_established_detail_style() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)
    canvas = _StrokeCanvas()
    renderer = ReportLabPdfRenderer()

    renderer._draw_face_outline(cast(Canvas, canvas), dimensions)
    renderer._draw_hole(
        cast(Canvas, canvas),
        CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("9")),
        dimensions,
    )
    renderer._draw_line(
        cast(Canvas, canvas),
        LineSegment(
            Face.A,
            Point(Decimal("-5"), Decimal("0")),
            Point(Decimal("5"), Decimal("0")),
        ),
        dimensions,
    )

    assert canvas.line_widths == [
        DETAIL_DRAWING_STYLE.face_outline_stroke_width,
        DETAIL_DRAWING_STYLE.feature_stroke_width,
        DETAIL_DRAWING_STYLE.crosshair_stroke_width,
        DETAIL_DRAWING_STYLE.construction_line_stroke_width,
    ]
    assert canvas.circle_count == 1
    assert canvas.circle_options == [{"stroke": 1, "fill": 0}]
    assert canvas.line_count == 3
    assert canvas.centered_strings == ["9"]
    assert canvas.fill_grays == []


def test_custom_overview_style_does_not_change_detail_page_style() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)
    canvas = _StrokeCanvas()
    renderer = ReportLabPdfRenderer(
        overview_style=replace(OVERVIEW_DRAWING_STYLE, feature_stroke_width=0.2)
    )

    renderer._draw_hole(
        cast(Canvas, canvas),
        CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("9")),
        dimensions,
    )

    assert canvas.line_widths == [
        DETAIL_DRAWING_STYLE.feature_stroke_width,
        DETAIL_DRAWING_STYLE.crosshair_stroke_width,
    ]


def test_overview_construction_lines_remain_unfilled_strokes() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    overview_face = enclosure_overview_geometry(enclosure).face_for(Face.A)
    canvas = _StrokeCanvas()

    ReportLabPdfRenderer()._draw_overview_line(
        cast(Canvas, canvas),
        LineSegment(
            Face.A,
            Point(Decimal("-5"), Decimal("0")),
            Point(Decimal("5"), Decimal("0")),
        ),
        overview_face,
    )

    assert canvas.line_count == 1
    assert canvas.fill_grays == []
    assert canvas.paths == []


def test_compound_tayda_capsule_renders_as_one_closed_outline_path() -> None:
    template = TaydaTxtParser().parse_file(
        Path(__file__).parent / "data" / "tayda_compound_capsule.txt"
    )
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    overview_face = enclosure_overview_geometry(enclosure).face_for(Face.A)
    feature = next(
        item
        for item in overview_features(template, Face.A)
        if isinstance(item, OverviewCompoundOutline)
    )
    canvas = _StrokeCanvas()

    ReportLabPdfRenderer()._draw_overview_feature(
        cast(Canvas, canvas), feature, overview_face
    )

    assert canvas.circle_count == 0
    assert canvas.line_count == 0
    assert len(canvas.paths) == 1
    assert canvas.fill_grays == [1.0]
    assert canvas.path_options == [{"stroke": 1, "fill": 1}]
    assert canvas.paths[0].operations == [
        "move",
        "line",
        "arc",
        "line",
        "arc",
    ]
