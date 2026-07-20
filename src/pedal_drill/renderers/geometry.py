"""Compatibility imports for geometry moved to the shared domain layer."""

from pedal_drill.geometry import (
    CalibrationLine,
    CalibrationOrientation,
    Capsule,
    PREFERRED_CALIBRATION_LENGTHS_MM,
    Rectangle,
    calibration_lines,
    capsule_bounds,
    capsule_for_slot,
    circle_bounds,
    face_bounds,
    face_corner_radius,
    face_outline,
    face_point,
    line_bounds,
    select_calibration_length,
)

__all__ = [
    "Capsule",
    "CalibrationLine",
    "CalibrationOrientation",
    "PREFERRED_CALIBRATION_LENGTHS_MM",
    "Rectangle",
    "calibration_lines",
    "capsule_bounds",
    "capsule_for_slot",
    "circle_bounds",
    "face_bounds",
    "face_corner_radius",
    "face_outline",
    "face_point",
    "line_bounds",
    "select_calibration_length",
]
