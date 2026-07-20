"""Validate drill geometry against data-driven enclosure face dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pedal_drill.enclosures.model import EnclosureDefinition
from pedal_drill.model import CircularHole, DrillTemplate, Face, LineSegment, Slot
from pedal_drill.geometry import (
    Capsule,
    Rectangle,
    capsule_bounds,
    circle_bounds,
    face_bounds,
    line_bounds,
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
        bounds = face_bounds(enclosure.dimensions_for(face))
        for hole in template.holes_on(face):
            _validate_circle(hole, enclosure.identifier, bounds)
        for slot in _slots_on(template, face):
            _validate_slot(slot, enclosure.identifier, bounds)
        for line in _lines_on(template, face):
            _validate_line(line, enclosure.identifier, bounds)


def _validate_circle(
    hole: CircularHole, enclosure_id: str, bounds: Rectangle
) -> None:
    _raise_if_outside(
        enclosure_id=enclosure_id,
        face=hole.face,
        feature_type="circular hole",
        position=_point_text(hole.center.x, hole.center.y),
        dimensions=f"diameter {hole.diameter} mm",
        feature_bounds=circle_bounds(hole),
        face_bounds_value=bounds,
    )


def _validate_slot(slot: Slot, enclosure_id: str, bounds: Rectangle) -> None:
    capsule = Capsule(
        center=slot.center,
        length=slot.length,
        width=slot.width,
        angle_degrees=slot.angle_degrees,
    )
    _raise_if_outside(
        enclosure_id=enclosure_id,
        face=slot.face,
        feature_type="rounded slot",
        position=_point_text(slot.center.x, slot.center.y),
        dimensions=(
            f"length {slot.length} mm, width {slot.width} mm, "
            f"angle {slot.angle_degrees} degrees"
        ),
        feature_bounds=capsule_bounds(capsule),
        face_bounds_value=bounds,
    )


def _validate_line(
    line: LineSegment, enclosure_id: str, bounds: Rectangle
) -> None:
    _raise_if_outside(
        enclosure_id=enclosure_id,
        face=line.face,
        feature_type="construction line",
        position=(
            f"start {_point_text(line.start.x, line.start.y)}, "
            f"end {_point_text(line.end.x, line.end.y)}"
        ),
        dimensions="zero-width line",
        feature_bounds=line_bounds(line),
        face_bounds_value=bounds,
    )


def _raise_if_outside(
    *,
    enclosure_id: str,
    face: Face,
    feature_type: str,
    position: str,
    dimensions: str,
    feature_bounds: Rectangle,
    face_bounds_value: Rectangle,
) -> None:
    exceeded = feature_bounds.exceeded_boundaries(
        face_bounds_value, GEOMETRY_TOLERANCE_MM
    )
    if exceeded:
        raise DrillLayoutOutsideEnclosureError(
            enclosure_id=enclosure_id,
            face=face,
            feature_type=feature_type,
            position=position,
            dimensions=dimensions,
            exceeded_boundaries=exceeded,
        )


def _point_text(x: Decimal, y: Decimal) -> str:
    return f"(x={x} mm, y={y} mm)"


def _slots_on(template: DrillTemplate, face: Face) -> tuple[Slot, ...]:
    return tuple(slot for slot in template.slots if slot.face is face)


def _lines_on(template: DrillTemplate, face: Face) -> tuple[LineSegment, ...]:
    return tuple(line for line in template.lines if line.face is face)
