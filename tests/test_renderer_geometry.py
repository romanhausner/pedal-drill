from decimal import Decimal
from typing import cast

from reportlab.pdfgen.canvas import Canvas

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.model import Face, Point, Slot
from pedal_drill.renderers.geometry import (
    PREFERRED_CALIBRATION_LENGTHS_MM,
    CalibrationLine,
    CalibrationOrientation,
    Capsule,
    calibration_lines,
    capsule_for_slot,
    capsule_path,
    face_outline,
    face_point,
    select_calibration_length,
)
from pedal_drill.renderers.pdf import ReportLabPdfRenderer


def test_face_geometry_uses_the_definition_dimensions_and_page_margin() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)

    outline = face_outline(dimensions, Decimal("10"))
    center = face_point(Point(Decimal("0"), Decimal("0")), dimensions, Decimal("10"))

    assert outline.width == Decimal("121.20")
    assert outline.height == Decimal("145.20")
    assert (outline.x, outline.y) == (Decimal("10"), Decimal("10"))
    assert center == Point(Decimal("70.60"), Decimal("82.60"))


def test_slot_geometry_preserves_size_and_orientation() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)
    slot = Slot(
        face=Face.A,
        center=Point(Decimal("5"), Decimal("-10")),
        length=Decimal("18"),
        width=Decimal("6"),
        angle_degrees=Decimal("45"),
    )

    capsule = capsule_for_slot(slot, dimensions, Decimal("10"))

    assert capsule.length == Decimal("18")
    assert capsule.width == Decimal("6")
    assert capsule.angle_degrees == Decimal("45")
    assert capsule.corner_radius == Decimal("3")


def test_slot_path_is_one_closed_capsule_contour() -> None:
    contour = capsule_path(
        Capsule(
            center=Point(Decimal("12"), Decimal("34")),
            length=Decimal("18"),
            width=Decimal("6"),
            angle_degrees=Decimal("27"),
        )
    )

    assert contour.is_closed
    assert contour.start == Point(Decimal("6"), Decimal("3"))
    assert contour.first_side_end == Point(Decimal("-6"), Decimal("3"))
    assert contour.second_side_end == Point(Decimal("6"), Decimal("-3"))
    assert contour.first_end_arc.center == Point(Decimal("-6"), Decimal("0"))
    assert contour.second_end_arc.center == Point(Decimal("6"), Decimal("0"))
    assert contour.first_end_arc.sweep_degrees == Decimal("180")
    assert contour.second_end_arc.sweep_degrees == Decimal("180")


def test_calibration_lengths_are_preferred_and_fit_face_dimensions() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)

    horizontal, vertical = calibration_lines(dimensions, Decimal("10"))

    assert horizontal.length == Decimal("100")
    assert vertical.length == Decimal("100")
    assert horizontal.orientation is CalibrationOrientation.HORIZONTAL
    assert vertical.orientation is CalibrationOrientation.VERTICAL
    assert horizontal.length in PREFERRED_CALIBRATION_LENGTHS_MM
    assert vertical.length in PREFERRED_CALIBRATION_LENGTHS_MM
    assert horizontal.length <= dimensions.width
    assert vertical.length <= dimensions.height
    assert horizontal.length >= Decimal("20")
    assert vertical.length >= Decimal("20")


def test_small_face_uses_shorter_calibration_lengths() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590a")
    dimensions = enclosure.dimensions_for(Face.B)

    horizontal, vertical = calibration_lines(dimensions, Decimal("10"))

    assert horizontal.length == Decimal("30")
    assert vertical.length == Decimal("30")
    assert select_calibration_length(Decimal("20")) == Decimal("20")
    assert select_calibration_length(Decimal("19.999")) is None


class _RecordingCanvas:
    def __init__(self) -> None:
        self.lines: list[tuple[float, float, float, float]] = []
        self.labels: list[str] = []
        self.translations: list[tuple[float, float]] = []

    def setFont(self, _: str, __: float) -> None:  # noqa: N802
        pass

    def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.lines.append((x1, y1, x2, y2))

    def drawCentredString(self, _: float, __: float, text: str) -> None:  # noqa: N802
        self.labels.append(text)

    def drawString(self, _: float, __: float, text: str) -> None:  # noqa: N802
        self.labels.append(text)

    def saveState(self) -> None:  # noqa: N802
        pass

    def translate(self, x: float, y: float) -> None:
        self.translations.append((x, y))

    def rotate(self, _: float) -> None:
        pass

    def restoreState(self) -> None:  # noqa: N802
        pass


def test_renderer_draws_both_calibration_lines() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)
    canvas = _RecordingCanvas()

    ReportLabPdfRenderer()._draw_calibration_lines(cast(Canvas, canvas), dimensions)

    assert len(canvas.lines) == 6
    assert canvas.labels == ["100 mm", "100 mm"]


def test_vertical_calibration_label_is_offset_from_the_line() -> None:
    canvas = _RecordingCanvas()
    line = CalibrationLine(
        start=Point(Decimal("5"), Decimal("20")),
        end=Point(Decimal("5"), Decimal("80")),
        orientation=CalibrationOrientation.VERTICAL,
    )
    renderer = ReportLabPdfRenderer()

    renderer._draw_calibration_line(cast(Canvas, canvas), line)

    label_x, label_y = canvas.translations[-1]
    assert label_x == renderer._points(Decimal("2"))
    assert label_y == renderer._points(Decimal("50"))
    assert label_x < renderer._points(line.start.x)
