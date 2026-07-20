"""A minimal, 1:1 PDF renderer for enclosure drill templates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from reportlab.pdfgen.canvas import Canvas

from pedal_drill.enclosures.model import EnclosureDefinition, FaceDimensions
from pedal_drill.enclosures.validation import validate_template_fits_enclosure
from pedal_drill.model import CircularHole, DrillTemplate, Face, LineSegment, Slot
from pedal_drill.geometry import (
    Capsule,
    capsule_for_slot,
    face_corner_radius,
    face_outline,
    face_point,
)

_POINTS_PER_MILLIMETRE = Decimal("72") / Decimal("25.4")
_DEFAULT_MARGIN_MM = Decimal("10")
_CROSSHAIR_HALF_LENGTH_MM = Decimal("2")
_HOLE_LABEL_GAP_MM = Decimal("2")
_REFERENCE_LENGTH_MM = Decimal("100")
_REFERENCE_TICK_HALF_LENGTH_MM = Decimal("2")


class PdfRenderError(ValueError):
    """Raised when a template cannot be rendered onto its enclosure geometry."""


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """Metadata for one generated face page, kept in the application's base unit."""

    face: Face
    width: Decimal
    height: Decimal


class ReportLabPdfRenderer:
    """Render every populated enclosure face as a separate, 1:1 PDF page."""

    def __init__(self, margin: Decimal = _DEFAULT_MARGIN_MM) -> None:
        if margin <= 0:
            raise ValueError("The PDF margin must be greater than zero.")
        self._margin = margin

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

        populated_faces = tuple(
            face
            for face in Face
            if (
                template.holes_on(face)
                or self._lines_on(template, face)
                or self._slots_on(template, face)
            )
        )
        if not populated_faces:
            raise PdfRenderError("Cannot render a template without features.")

        validate_template_fits_enclosure(template, enclosure)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = Canvas(str(output_path))
        pages: list[RenderedPage] = []
        for face in populated_faces:
            dimensions = enclosure.dimensions_for(face)
            page = self._page_for(face, dimensions)
            canvas.setPageSize((self._points(page.width), self._points(page.height)))
            self._draw_page(canvas, template, enclosure, page, dimensions)
            canvas.showPage()
            pages.append(page)
        canvas.save()
        return tuple(pages)

    def _page_for(self, face: Face, dimensions: FaceDimensions) -> RenderedPage:
        return RenderedPage(
            face=face,
            width=dimensions.width + (self._margin * 2),
            height=dimensions.height + (self._margin * 2),
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
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(
            self._points(page.width / 2),
            self._points(title_y),
            f"{enclosure.model} - Face {page.face.value}",
        )
        self._draw_reference_line(canvas, page, dimensions)
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
        point = face_point(hole.center, dimensions, self._margin)
        x, y = point.x, point.y
        radius = hole.diameter / 2
        canvas.circle(self._points(x), self._points(y), self._points(radius))
        half = _CROSSHAIR_HALF_LENGTH_MM
        canvas.line(
            self._points(x - half),
            self._points(y),
            self._points(x + half),
            self._points(y),
        )
        canvas.line(
            self._points(x),
            self._points(y - half),
            self._points(x),
            self._points(y + half),
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
        start = face_point(line.start, dimensions, self._margin)
        end = face_point(line.end, dimensions, self._margin)
        canvas.line(
            self._points(start.x),
            self._points(start.y),
            self._points(end.x),
            self._points(end.y),
        )

    def _draw_slot(
        self, canvas: Canvas, slot: Slot, dimensions: FaceDimensions
    ) -> None:
        capsule = capsule_for_slot(slot, dimensions, self._margin)
        self._draw_capsule(canvas, capsule)

    def _draw_capsule(self, canvas: Canvas, capsule: Capsule) -> None:
        """Draw a rotated capsule without exposing ReportLab to domain geometry."""

        canvas.saveState()
        canvas.translate(self._points(capsule.center.x), self._points(capsule.center.y))
        canvas.rotate(float(capsule.angle_degrees))
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

    def _draw_face_outline(self, canvas: Canvas, dimensions: FaceDimensions) -> None:
        outline = face_outline(dimensions, self._margin)
        canvas.roundRect(
            self._points(outline.x),
            self._points(outline.y),
            self._points(outline.width),
            self._points(outline.height),
            self._points(face_corner_radius(dimensions)),
            stroke=1,
            fill=0,
        )

    def _draw_reference_line(
        self, canvas: Canvas, page: RenderedPage, dimensions: FaceDimensions
    ) -> None:
        """Draw a 100 mm line in a margin, using its longest fitting orientation."""

        canvas.setFont("Helvetica", 7)
        if dimensions.width >= _REFERENCE_LENGTH_MM:
            start_x = (page.width - _REFERENCE_LENGTH_MM) / 2
            end_x = start_x + _REFERENCE_LENGTH_MM
            y = self._margin / 2
            canvas.line(
                self._points(start_x),
                self._points(y),
                self._points(end_x),
                self._points(y),
            )
            self._draw_vertical_tick(canvas, start_x, y)
            self._draw_vertical_tick(canvas, end_x, y)
            canvas.drawCentredString(
                self._points(page.width / 2),
                self._points(y + Decimal("1")),
                "100 mm",
            )
            return
        if dimensions.height >= _REFERENCE_LENGTH_MM:
            x = self._margin / 2
            start_y = (page.height - _REFERENCE_LENGTH_MM) / 2
            end_y = start_y + _REFERENCE_LENGTH_MM
            canvas.line(
                self._points(x),
                self._points(start_y),
                self._points(x),
                self._points(end_y),
            )
            self._draw_horizontal_tick(canvas, x, start_y)
            self._draw_horizontal_tick(canvas, x, end_y)
            canvas.drawString(
                self._points(x + Decimal("1")), self._points(page.height / 2), "100 mm"
            )
            return
        raise PdfRenderError(
            "The enclosure face is too small to include the required 100 mm "
            "reference line."
        )

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

    @staticmethod
    def _points(value: Decimal) -> float:
        """Convert millimetres to PDF points at the ReportLab drawing boundary."""

        return float(value * _POINTS_PER_MILLIMETRE)
