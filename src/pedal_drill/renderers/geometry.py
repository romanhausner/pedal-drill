"""Compatibility imports for geometry moved to the shared domain layer."""

from pedal_drill.geometry import (
    Capsule,
    Rectangle,
    capsule_bounds,
    capsule_for_slot,
    circle_bounds,
    face_bounds,
    face_corner_radius,
    face_outline,
    face_point,
    line_bounds,
)

__all__ = [
    "Capsule",
    "Rectangle",
    "capsule_bounds",
    "capsule_for_slot",
    "circle_bounds",
    "face_bounds",
    "face_corner_radius",
    "face_outline",
    "face_point",
    "line_bounds",
]
