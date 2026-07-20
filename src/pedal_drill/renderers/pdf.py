"""A minimal, 1:1 PDF renderer for enclosure drill templates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

from pedal_drill.enclosures.model import EnclosureDefinition, FaceDimensions
from pedal_drill.enclosures.validation import validate_template_fits_enclosure
from pedal_drill.geometry import (
    CalibrationLine,
    CalibrationOrientation,
    Capsule,
    EnclosureOverview,
    OverviewFace,
    calibration_lines,
    capsule_for_slot,
    enclosure_overview_geometry,
    face_corner_radius,
    face_outline,
    face_point,
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
from pedal_drill.overview import (
    OverviewArc,
    OverviewCapsule,
    OverviewCircle,
    OverviewCompoundOutline,
    OverviewLine,
    overview_features,
)
from pedal_drill.renderers.styles import (
    DETAIL_DRAWING_STYLE,
    OVERVIEW_DRAWING_STYLE,
    DrawingStyle,
    FeatureRendering,
)

_POINTS_PER_MILLIMETRE = Decimal("72") / Decimal("25.4")
_DEFAULT_MARGIN_MM = Decimal("10")
_HOLE_LABEL_GAP_MM = Decimal("2")
_REFERENCE_TICK_HALF_LENGTH_MM = Decimal("2")
_HORIZONTAL_LABEL_GAP_MM = Decimal("1")
_VERTICAL_LABEL_GAP_MM = Decimal("3")
_INSTRUCTION_GUTTER_MM = Decimal("10")
_INSTRUCTION_FONT_SIZE = 5.5
_INSTRUCTION_LINE_HEIGHT_MM = Decimal("2.5")
_OVERVIEW_SCALE = Decimal("0.375")
_OVERVIEW_MARGIN_MM = Decimal("20")
_OVERVIEW_NOTE_FONT_SIZE = 6
_PRINT_INSTRUCTIONS = (
    "Print at 100% scale.",
    'Disable scaling or "Fit to page".',
    "Verify both calibration lines before drilling.",
)


class PdfRenderError(ValueError):
    """Raised when a template cannot be rendered onto its enclosure geometry."""


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """Metadata for one generated PDF page, kept in the base unit."""

    face: Face | None
    width: Decimal
    height: Decimal
    is_overview: bool = False


class ReportLabPdfRenderer:
    """Render an enclosure overview plus 1:1 pages for its populated faces."""

    def __init__(
        self,
        margin: Decimal = _DEFAULT_MARGIN_MM,
        *,
        detail_style: DrawingStyle = DETAIL_DRAWING_STYLE,
        overview_style: DrawingStyle = OVERVIEW_DRAWING_STYLE,
    ) -> None:
        if margin <= 0:
            raise ValueError("The PDF margin must be greater than zero.")
        self._margin = margin
        self._bottom_margin = margin + _INSTRUCTION_GUTTER_MM
        self._detail_style = detail_style
        self._overview_style = overview_style

    def render(
        self,
        template: DrillTemplate,
        enclosure: EnclosureDefinition,
        output_path: Path,
    ) -> tuple[RenderedPage, ...]:
        """Write a 1:1 PDF and return page metadata in millimetres.

        Only conversions performed immediately before ReportLab drawing calls
        turn millimetres into PDF points.
        """

        populated_faces = self._populated_faces(template)
        if not populated_faces:
            raise PdfRenderError("Cannot render a template without features.")

        validate_template_fits_enclosure(template, enclosure)
        self._validate_calibration_lines(populated_faces, enclosure)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Canvas(str(output_path))
        pages: list[RenderedPage] = []
        overview = enclosure_overview_geometry(
            enclosure,
            scale=_OVERVIEW_SCALE,
            margin=_OVERVIEW_MARGIN_MM,
        )
        overview_page = RenderedPage(
            face=None,
            width=overview.page_bounds.width,
            height=overview.page_bounds.height,
            is_overview=True,
        )
        canvas.setPageSize(
            (self._points(overview_page.width), self._points(overview_page.height))
        )
        self._draw_overview_page(canvas, template, enclosure, overview)
        canvas.showPage()
        pages.append(overview_page)
        for face in populated_faces:
            dimensions = enclosure.dimensions_for(face)
            page = self._page_for(face, dimensions)
            canvas.setPageSize((self._points(page.width), self._points(page.height)))
            self._draw_page(canvas, template, enclosure, page, dimensions)
            canvas.showPage()
            pages.append(page)
        canvas.save()
        return tuple(pages)

    def _draw_overview_page(
        self,
        canvas: Canvas,
        template: DrillTemplate,
        enclosure: EnclosureDefinition,
        overview: EnclosureOverview,
    ) -> None:
        """Draw a reduced outside-view net used only to orient the drill plan."""

        page = overview.page_bounds
        populated_faces = self._populated_faces(template)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawString(
            self._points(_OVERVIEW_MARGIN_MM),
            self._points(page.height - Decimal("7")),
            enclosure.model,
        )
        canvas.setFont("Helvetica", 5.5)
        canvas.drawString(
            self._points(_OVERVIEW_MARGIN_MM),
            self._points(page.height - Decimal("11")),
            f"Outside view | {len(populated_faces)} populated faces",
        )
        for overview_face in overview.faces:
            self._draw_overview_face(
                canvas,
                template,
                enclosure,
                overview_face,
                is_populated=overview_face.face in populated_faces,
            )
        canvas.setFont("Helvetica", _OVERVIEW_NOTE_FONT_SIZE)
        canvas.drawCentredString(
            self._points(page.width / 2),
            self._points(Decimal("3")),
            "Orientation overview - not to scale for drilling.",
        )

    def _draw_overview_face(
        self,
        canvas: Canvas,
        template: DrillTemplate,
        enclosure: EnclosureDefinition,
        overview_face: OverviewFace,
        *,
        is_populated: bool,
    ) -> None:
        """Draw one outlined face and its locally transformed drill features."""

        bounds = overview_face.bounds
        dimensions = enclosure.dimensions_for(overview_face.face)
        if is_populated and self._overview_style.face_fill_gray is not None:
            canvas.saveState()
            canvas.setFillGray(self._overview_style.face_fill_gray)
            canvas.roundRect(
                self._points(bounds.x),
                self._points(bounds.y),
                self._points(bounds.width),
                self._points(bounds.height),
                self._points(
                    face_corner_radius(dimensions) * overview_face.transform.scale
                ),
                stroke=0,
                fill=1,
            )
            canvas.restoreState()
        canvas.setLineWidth(self._overview_style.face_outline_stroke_width)
        canvas.roundRect(
            self._points(bounds.x),
            self._points(bounds.y),
            self._points(bounds.width),
            self._points(bounds.height),
            self._points(
                face_corner_radius(dimensions) * overview_face.transform.scale
            ),
            stroke=1,
            fill=0,
        )
        self._draw_overview_face_label(canvas, overview_face)
        for feature in overview_features(template, overview_face.face):
            self._draw_overview_feature(canvas, feature, overview_face)

    def _draw_overview_feature(
        self,
        canvas: Canvas,
        feature: (
            OverviewCircle | OverviewCapsule | OverviewCompoundOutline | OverviewLine
        ),
        overview_face: OverviewFace,
    ) -> None:
        """Draw one normalized overview primitive in its face-local transform."""

        if isinstance(feature, OverviewCircle):
            self._draw_overview_circle(
                canvas,
                feature.center,
                feature.diameter,
                overview_face,
            )
            return
        if isinstance(feature, OverviewCapsule):
            self._draw_overview_capsule(
                canvas,
                transform_overview_capsule(feature.capsule, overview_face),
                self._overview_style,
            )
            return
        if isinstance(feature, OverviewCompoundOutline):
            self._draw_overview_compound_outline(canvas, feature, overview_face)
            return
        self._draw_overview_line(
            canvas,
            LineSegment(overview_face.face, feature.start, feature.end),
            overview_face,
        )

    def _draw_overview_hole(
        self,
        canvas: Canvas,
        hole: CircularHole,
        overview_face: OverviewFace,
    ) -> None:
        """Draw a scaled hole symbol without a detailed-page diameter label."""

        self._draw_overview_circle(
            canvas,
            hole.center,
            hole.diameter,
            overview_face,
        )

    def _draw_overview_circle(
        self,
        canvas: Canvas,
        center: Point,
        diameter: Decimal,
        overview_face: OverviewFace,
    ) -> None:
        """Draw one ordinary overview circle without drilling-aid annotations."""

        point = overview_face.transform.point(center)
        radius = diameter * overview_face.transform.scale / 2
        canvas.saveState()
        self._draw_circle_feature(canvas, point, radius, self._overview_style)
        canvas.restoreState()

    def _draw_overview_line(
        self,
        canvas: Canvas,
        line: LineSegment,
        overview_face: OverviewFace,
    ) -> None:
        """Draw a construction line in the overview face's local transform."""

        start = overview_face.transform.point(line.start)
        end = overview_face.transform.point(line.end)
        canvas.setLineWidth(self._overview_style.construction_line_stroke_width)
        canvas.line(
            self._points(start.x),
            self._points(start.y),
            self._points(end.x),
            self._points(end.y),
        )

    def _draw_overview_face_label(
        self, canvas: Canvas, overview_face: OverviewFace
    ) -> None:
        """Draw labels without letting narrow side faces spill into their neighbours."""

        bounds = overview_face.bounds
        label = _overview_face_label(overview_face.face)
        canvas.setFont("Helvetica", self._overview_style.face_label_font_size)
        if overview_face.face in (Face.A, Face.C, Face.E):
            canvas.saveState()
            canvas.translate(
                self._points(bounds.x + Decimal("3")),
                self._points(bounds.y + (bounds.height / 2)),
            )
            canvas.rotate(90)
            canvas.drawCentredString(0, 0, label)
            canvas.restoreState()
            return
        label_y = bounds.y + bounds.height - Decimal("3")
        canvas.drawString(
            self._points(bounds.x + Decimal("1")), self._points(label_y), label
        )

    def _page_for(self, face: Face, dimensions: FaceDimensions) -> RenderedPage:
        return RenderedPage(
            face=face,
            width=dimensions.width + (self._margin * 2),
            height=dimensions.height + self._margin + self._bottom_margin,
        )

    def _draw_page(
        self,
        canvas: Canvas,
        template: DrillTemplate,
        enclosure: EnclosureDefinition,
        page: RenderedPage,
        dimensions: FaceDimensions,
    ) -> None:
        title_y = page.height - (self._margin / 2)
        canvas.setFont("Helvetica", self._detail_style.face_label_font_size)
        canvas.drawCentredString(
            self._points(page.width / 2),
            self._points(title_y),
            f"{enclosure.model} - Face {page.face.value}",
        )
        self._draw_calibration_lines(canvas, dimensions)
        self._draw_instructions(canvas, page)
        self._draw_face_outline(canvas, dimensions)
        for line in self._lines_on(template, page.face):
            self._draw_line(canvas, line, dimensions)
        for slot in self._slots_on(template, page.face):
            self._draw_slot(canvas, slot, dimensions)
        for hole in template.holes_on(page.face):
            self._draw_hole(canvas, hole, dimensions)

    def _draw_hole(
        self, canvas: Canvas, hole: CircularHole, dimensions: FaceDimensions
    ) -> None:
        point = face_point(
            hole.center,
            dimensions,
            self._margin,
            self._bottom_margin,
        )
        x, y = point.x, point.y
        radius = hole.diameter / 2
        self._draw_circle_feature(
            canvas,
            Point(x, y),
            radius,
            self._detail_style,
        )
        canvas.setFont("Helvetica", 6)
        canvas.drawCentredString(
            self._points(x),
            self._points(y - radius - _HOLE_LABEL_GAP_MM),
            str(hole.diameter),
        )

    def _draw_line(
        self, canvas: Canvas, line: LineSegment, dimensions: FaceDimensions
    ) -> None:
        start = face_point(line.start, dimensions, self._margin, self._bottom_margin)
        end = face_point(line.end, dimensions, self._margin, self._bottom_margin)
        canvas.setLineWidth(self._detail_style.construction_line_stroke_width)
        canvas.line(
            self._points(start.x),
            self._points(start.y),
            self._points(end.x),
            self._points(end.y),
        )

    def _draw_slot(
        self, canvas: Canvas, slot: Slot, dimensions: FaceDimensions
    ) -> None:
        capsule = capsule_for_slot(
            slot,
            dimensions,
            self._margin,
            self._bottom_margin,
        )
        self._draw_capsule(canvas, capsule, self._detail_style)

    def _draw_capsule(
        self, canvas: Canvas, capsule: Capsule, style: DrawingStyle
    ) -> None:
        """Draw a rotated capsule without exposing ReportLab to domain geometry."""

        canvas.saveState()
        canvas.translate(self._points(capsule.center.x), self._points(capsule.center.y))
        canvas.rotate(float(capsule.angle_degrees))
        canvas.setLineWidth(style.feature_stroke_width)
        self._set_closed_feature_fill(canvas, style)
        canvas.roundRect(
            self._points(-capsule.length / 2),
            self._points(-capsule.width / 2),
            self._points(capsule.length),
            self._points(capsule.width),
            self._points(capsule.corner_radius),
            stroke=1,
            fill=0,
        )
        canvas.restoreState()

    def _draw_overview_capsule(
        self, canvas: Canvas, capsule: Capsule, style: DrawingStyle
    ) -> None:
        """Stroke one closed capsule path without endpoint-circle construction aids."""

        radius = capsule.corner_radius
        half_centerline = (capsule.length - capsule.width) / 2
        canvas.saveState()
        canvas.translate(self._points(capsule.center.x), self._points(capsule.center.y))
        canvas.rotate(float(capsule.angle_degrees))
        canvas.setLineWidth(style.feature_stroke_width)
        self._set_closed_feature_fill(canvas, style)
        path = canvas.beginPath()
        path.moveTo(self._points(half_centerline), self._points(radius))
        path.lineTo(self._points(-half_centerline), self._points(radius))
        path.arc(
            self._points(-half_centerline - radius),
            self._points(-radius),
            self._points(-half_centerline + radius),
            self._points(radius),
            90,
            180,
        )
        path.lineTo(self._points(half_centerline), self._points(-radius))
        path.arc(
            self._points(half_centerline - radius),
            self._points(-radius),
            self._points(half_centerline + radius),
            self._points(radius),
            270,
            180,
        )
        path.close()
        canvas.drawPath(path, stroke=1, fill=self._closed_feature_fill_enabled(style))
        canvas.restoreState()

    def _draw_overview_compound_outline(
        self,
        canvas: Canvas,
        outline: OverviewCompoundOutline,
        overview_face: OverviewFace,
    ) -> None:
        """Draw imported compound sides joined by their calculated exterior arcs."""

        first_arc = outline.first_end_arc
        second_arc = outline.second_end_arc
        canvas.saveState()
        canvas.setLineWidth(self._overview_style.feature_stroke_width)
        self._set_closed_feature_fill(canvas, self._overview_style)
        path = canvas.beginPath()
        start = overview_face.transform.point(outline.first_side.start)
        path.moveTo(self._points(start.x), self._points(start.y))
        self._path_line_to(path, outline.first_side.end, overview_face)
        self._path_arc(path, second_arc, overview_face)
        self._path_line_to(path, outline.second_side.start, overview_face)
        self._path_arc(path, first_arc, overview_face)
        # The final arc ends exactly at the first side's start point.  Do not
        # call close(): a PDF close command may otherwise add a diagonal edge.
        canvas.drawPath(
            path,
            stroke=1,
            fill=self._closed_feature_fill_enabled(self._overview_style),
        )
        canvas.restoreState()

    def _path_line_to(
        self, path: object, point: Point, overview_face: OverviewFace
    ) -> None:
        """Append one transformed boundary line to a normalized overview path."""

        transformed = overview_face.transform.point(point)
        path.lineTo(self._points(transformed.x), self._points(transformed.y))

    def _path_arc(
        self, path: object, arc: OverviewArc, overview_face: OverviewFace
    ) -> None:
        """Append a uniformly transformed exterior circular arc to a PDF path."""

        center = overview_face.transform.point(arc.center)
        radius = arc.radius * overview_face.transform.scale
        path.arc(
            self._points(center.x - radius),
            self._points(center.y - radius),
            self._points(center.x + radius),
            self._points(center.y + radius),
            float(arc.start_angle_degrees),
            float(arc.sweep_degrees),
        )

    def _draw_circle_feature(
        self,
        canvas: Canvas,
        center: Point,
        radius: Decimal,
        style: DrawingStyle,
    ) -> None:
        """Draw a hole outline, adding crosshairs only for a drilling-aid style."""

        canvas.setLineWidth(style.feature_stroke_width)
        self._set_closed_feature_fill(canvas, style)
        canvas.circle(
            self._points(center.x),
            self._points(center.y),
            self._points(radius),
            stroke=1,
            fill=self._closed_feature_fill_enabled(style),
        )
        if style.feature_rendering is FeatureRendering.OUTLINES_ONLY:
            return
        canvas.setLineWidth(style.crosshair_stroke_width)
        half = style.crosshair_half_length
        canvas.line(
            self._points(center.x - half),
            self._points(center.y),
            self._points(center.x + half),
            self._points(center.y),
        )
        canvas.line(
            self._points(center.x),
            self._points(center.y - half),
            self._points(center.x),
            self._points(center.y + half),
        )

    @staticmethod
    def _closed_feature_fill_enabled(style: DrawingStyle) -> int:
        """Return the ReportLab fill flag for a closed drill-feature symbol."""

        return int(style.closed_feature_fill_gray is not None)

    @staticmethod
    def _set_closed_feature_fill(canvas: Canvas, style: DrawingStyle) -> None:
        """Set a closed feature's fill independently of its containing face."""

        if style.closed_feature_fill_gray is not None:
            canvas.setFillGray(style.closed_feature_fill_gray)

    def _draw_face_outline(self, canvas: Canvas, dimensions: FaceDimensions) -> None:
        outline = face_outline(dimensions, self._margin, self._bottom_margin)
        canvas.setLineWidth(self._detail_style.face_outline_stroke_width)
        canvas.roundRect(
            self._points(outline.x),
            self._points(outline.y),
            self._points(outline.width),
            self._points(outline.height),
            self._points(face_corner_radius(dimensions)),
            stroke=1,
            fill=0,
        )

    def _draw_calibration_lines(
        self, canvas: Canvas, dimensions: FaceDimensions
    ) -> None:
        """Draw the horizontal and vertical calibration lines for a face page."""

        try:
            lines = calibration_lines(dimensions, self._margin, self._bottom_margin)
        except ValueError as error:
            raise PdfRenderError(str(error)) from error
        for line in lines:
            self._draw_calibration_line(canvas, line)

    def _validate_calibration_lines(
        self, faces: tuple[Face, ...], enclosure: EnclosureDefinition
    ) -> None:
        """Ensure calibration geometry is valid before an output file is opened."""

        try:
            for face in faces:
                calibration_lines(
                    enclosure.dimensions_for(face),
                    self._margin,
                    self._bottom_margin,
                )
        except ValueError as error:
            raise PdfRenderError(str(error)) from error

    def _draw_calibration_line(
        self, canvas: Canvas, line: CalibrationLine
    ) -> None:
        """Draw one dimension line, including its endpoint ticks and label."""

        canvas.setFont("Helvetica", 7)
        canvas.line(
            self._points(line.start.x),
            self._points(line.start.y),
            self._points(line.end.x),
            self._points(line.end.y),
        )
        if line.orientation is CalibrationOrientation.HORIZONTAL:
            self._draw_vertical_tick(canvas, line.start.x, line.start.y)
            self._draw_vertical_tick(canvas, line.end.x, line.end.y)
            label_position = self._calibration_label_position(line)
            canvas.drawCentredString(
                self._points(label_position.x),
                self._points(label_position.y),
                _calibration_label(line.length),
            )
            return
        if line.orientation is CalibrationOrientation.VERTICAL:
            self._draw_horizontal_tick(canvas, line.start.x, line.start.y)
            self._draw_horizontal_tick(canvas, line.end.x, line.end.y)
            label_position = self._calibration_label_position(line)
            canvas.saveState()
            canvas.translate(
                self._points(label_position.x),
                self._points(label_position.y),
            )
            canvas.rotate(90)
            canvas.drawCentredString(0, 0, _calibration_label(line.length))
            canvas.restoreState()
            return
        raise PdfRenderError(f"Unsupported calibration orientation: {line.orientation}")

    @staticmethod
    def _calibration_label_position(line: CalibrationLine) -> Point:
        """Return a centred label position with an orientation-specific gap."""

        midpoint = Point(
            (line.start.x + line.end.x) / 2,
            (line.start.y + line.end.y) / 2,
        )
        if line.orientation is CalibrationOrientation.HORIZONTAL:
            return Point(midpoint.x, midpoint.y + _HORIZONTAL_LABEL_GAP_MM)
        if line.orientation is CalibrationOrientation.VERTICAL:
            return Point(midpoint.x - _VERTICAL_LABEL_GAP_MM, midpoint.y)
        raise PdfRenderError(f"Unsupported calibration orientation: {line.orientation}")

    def _draw_instructions(self, canvas: Canvas, page: RenderedPage) -> None:
        """Draw a compact print reminder in the reserved bottom gutter."""

        canvas.setFont("Helvetica", _INSTRUCTION_FONT_SIZE)
        baseline = self._bottom_margin - Decimal("3")
        for instruction in _PRINT_INSTRUCTIONS:
            canvas.drawCentredString(
                self._points(page.width / 2),
                self._points(baseline),
                instruction,
            )
            baseline -= _INSTRUCTION_LINE_HEIGHT_MM

    def _draw_vertical_tick(self, canvas: Canvas, x: Decimal, y: Decimal) -> None:
        canvas.line(
            self._points(x),
            self._points(y - _REFERENCE_TICK_HALF_LENGTH_MM),
            self._points(x),
            self._points(y + _REFERENCE_TICK_HALF_LENGTH_MM),
        )

    def _draw_horizontal_tick(self, canvas: Canvas, x: Decimal, y: Decimal) -> None:
        canvas.line(
            self._points(x - _REFERENCE_TICK_HALF_LENGTH_MM),
            self._points(y),
            self._points(x + _REFERENCE_TICK_HALF_LENGTH_MM),
            self._points(y),
        )

    @staticmethod
    def _lines_on(template: DrillTemplate, face: Face) -> tuple[LineSegment, ...]:
        return tuple(line for line in template.lines if line.face is face)

    @staticmethod
    def _slots_on(template: DrillTemplate, face: Face) -> tuple[Slot, ...]:
        return tuple(slot for slot in template.slots if slot.face is face)

    @classmethod
    def _populated_faces(cls, template: DrillTemplate) -> tuple[Face, ...]:
        """Return faces that contain at least one drawable template feature."""

        return tuple(
            face
            for face in Face
            if (
                template.holes_on(face)
                or cls._lines_on(template, face)
                or cls._slots_on(template, face)
            )
        )

    @staticmethod
    def _points(value: Decimal) -> float:
        """Convert millimetres to PDF points at the ReportLab drawing boundary."""

        return float(value * _POINTS_PER_MILLIMETRE)


def _calibration_label(length: Decimal) -> str:
    """Format a preferred calibration length without unnecessary decimal places."""

    return f"{format(length.normalize(), 'f')} mm"


def _overview_face_label(face: Face) -> str:
    """Return the stable orientation label used by the unfolded overview."""

    names = {
        Face.A: "Front",
        Face.B: "Top",
        Face.C: "Left",
        Face.D: "Bottom",
        Face.E: "Right",
    }
    return f"Face {face.value} / {names[face]}"
