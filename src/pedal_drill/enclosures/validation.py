"""Validate drill geometry against data-driven enclosure face dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pedal_drill.enclosures.model import EnclosureDefinition
from pedal_drill.geometry import (
    Capsule,
    Polygon,
    capsule_centerline_endpoints,
    face_polygon,
    polygon_contains_capsule,
    polygon_contains_circle,
    polygon_contains_line,
    polygon_edge_clearances,
)
from pedal_drill.model import (
    CircularHole,
    DrillTemplate,
    Face,
    LineSegment,
    Point,
    Slot,
)

GEOMETRY_TOLERANCE_MM = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class DrillLayoutOutsideEnclosureError(ValueError):
    """A feature's complete geometry extends beyond its selected enclosure face."""

    enclosure_id: str
    face: Face
    feature_type: str
    position: str
    dimensions: str
    exceeded_boundaries: tuple[str, ...]

    def __str__(self) -> str:
        boundaries = ", ".join(self.exceeded_boundaries)
        return (
            f"Enclosure {self.enclosure_id}, face {self.face.value}: "
            f"{self.feature_type} at {self.position} with {self.dimensions} "
            f"exceeds the {boundaries} boundary or boundaries. "
            "The drill layout does not fit this enclosure."
        )


def validate_template_fits_enclosure(
    template: DrillTemplate, enclosure: EnclosureDefinition
) -> None:
    """Raise a dedicated error when any feature extends beyond its face bounds."""

    for face in Face:
        outline = face_polygon(enclosure.dimensions_for(face), face)
        for hole in template.holes_on(face):
            _validate_circle(hole, enclosure.identifier, outline)
        for slot in _slots_on(template, face):
            _validate_slot(slot, enclosure.identifier, outline)
        for line in _lines_on(template, face):
            _validate_line(line, enclosure.identifier, outline)


def _validate_circle(
    hole: CircularHole, enclosure_id: str, outline: Polygon
) -> None:
    radius = hole.diameter / 2
    if polygon_contains_circle(
        outline, hole.center, radius, GEOMETRY_TOLERANCE_MM
    ):
        return
    _raise_outside(
        enclosure_id=enclosure_id,
        face=hole.face,
        feature_type="circular hole",
        position=_point_text(hole.center.x, hole.center.y),
        dimensions=f"diameter {hole.diameter} mm",
        exceeded_boundaries=_exceeded_edges(outline, (hole.center,), radius),
    )


def _validate_slot(slot: Slot, enclosure_id: str, outline: Polygon) -> None:
    capsule = Capsule(
        center=slot.center,
        length=slot.length,
        width=slot.width,
        angle_degrees=slot.angle_degrees,
    )
    if polygon_contains_capsule(outline, capsule, GEOMETRY_TOLERANCE_MM):
        return
    _raise_outside(
        enclosure_id=enclosure_id,
        face=slot.face,
        feature_type="rounded slot",
        position=_point_text(slot.center.x, slot.center.y),
        dimensions=(
            f"length {slot.length} mm, width {slot.width} mm, "
            f"angle {slot.angle_degrees} degrees"
        ),
        exceeded_boundaries=_exceeded_edges(
            outline,
            capsule_centerline_endpoints(capsule),
            capsule.width / 2,
        ),
    )


def _validate_line(
    line: LineSegment, enclosure_id: str, outline: Polygon
) -> None:
    if polygon_contains_line(
        outline,
        line.start,
        line.end,
        GEOMETRY_TOLERANCE_MM,
    ):
        return
    _raise_outside(
        enclosure_id=enclosure_id,
        face=line.face,
        feature_type="construction line",
        position=(
            f"start {_point_text(line.start.x, line.start.y)}, "
            f"end {_point_text(line.end.x, line.end.y)}"
        ),
        dimensions="zero-width line",
        exceeded_boundaries=_exceeded_edges(
            outline,
            (line.start, line.end),
            Decimal("0"),
        ),
    )


def _raise_outside(
    *,
    enclosure_id: str,
    face: Face,
    feature_type: str,
    position: str,
    dimensions: str,
    exceeded_boundaries: tuple[str, ...],
) -> None:
    raise DrillLayoutOutsideEnclosureError(
        enclosure_id=enclosure_id,
        face=face,
        feature_type=feature_type,
        position=position,
        dimensions=dimensions,
        exceeded_boundaries=exceeded_boundaries or ("outline",),
    )


def _exceeded_edges(
    outline: Polygon,
    points: tuple[Point, ...],
    required_clearance: Decimal,
) -> tuple[str, ...]:
    exceeded: list[str] = []
    for index, edge in enumerate(outline.edges):
        if any(
            polygon_edge_clearances(point, outline)[index]
            < required_clearance - GEOMETRY_TOLERANCE_MM
            for point in points
        ):
            exceeded.append(_boundary_name(edge, index))
    return tuple(exceeded)


def _boundary_name(edge: tuple[Point, Point], index: int) -> str:
    """Name an edge from its transformed outward normal, not vertex order.

    Face polygons use clockwise winding, so the left-hand normal points out of
    the enclosure.  If that normal has no dominant axis, a neutral edge label
    avoids presenting an ambiguous diagonal as a precise direction.
    """

    start, end = edge
    outward_x = start.y - end.y
    outward_y = end.x - start.x
    if abs(outward_x) > abs(outward_y):
        return "right" if outward_x > 0 else "left"
    if abs(outward_y) > abs(outward_x):
        return "top" if outward_y > 0 else "bottom"
    return f"edge {index + 1}"


def _point_text(x: Decimal, y: Decimal) -> str:
    return f"(x={x} mm, y={y} mm)"


def _slots_on(template: DrillTemplate, face: Face) -> tuple[Slot, ...]:
    return tuple(slot for slot in template.slots if slot.face is face)


def _lines_on(template: DrillTemplate, face: Face) -> tuple[LineSegment, ...]:
    return tuple(line for line in template.lines if line.face is face)
