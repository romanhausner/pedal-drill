"""Reusable visual styles for technical enclosure drawings."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto


class FeatureRendering(Enum):
    """The level of drill-aid detail included in a feature symbol."""

    DRILLING_AIDS = auto()
    OUTLINES_ONLY = auto()


@dataclass(frozen=True, slots=True)
class DrawingStyle:
    """Line and marker measurements for one renderer presentation scale.

    Stroke widths are PDF points because they are passed directly to ReportLab.
    Geometry remains in the application's millimetre base unit, including the
    crosshair length.
    """

    face_outline_stroke_width: float
    feature_stroke_width: float
    construction_line_stroke_width: float
    crosshair_stroke_width: float
    crosshair_half_length: Decimal
    face_label_font_size: float
    feature_rendering: FeatureRendering
    face_fill_gray: float | None
    closed_feature_fill_gray: float | None


DETAIL_DRAWING_STYLE = DrawingStyle(
    face_outline_stroke_width=1.0,
    feature_stroke_width=1.0,
    construction_line_stroke_width=1.0,
    crosshair_stroke_width=1.0,
    crosshair_half_length=Decimal("2"),
    face_label_font_size=9.0,
    feature_rendering=FeatureRendering.DRILLING_AIDS,
    face_fill_gray=None,
    closed_feature_fill_gray=None,
)
"""The established full-size detail-page drawing style."""


OVERVIEW_DRAWING_STYLE = DrawingStyle(
    face_outline_stroke_width=0.5,
    feature_stroke_width=0.45,
    construction_line_stroke_width=0.4,
    crosshair_stroke_width=0.4,
    crosshair_half_length=Decimal("0.65"),
    face_label_font_size=6.0,
    feature_rendering=FeatureRendering.OUTLINES_ONLY,
    face_fill_gray=0.93,
    closed_feature_fill_gray=1.0,
)
"""A lighter style that keeps scaled drill features crisp and separate."""
