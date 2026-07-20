"""Unit-preserving geometry calculations shared by validation and renderers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto
from math import cos, radians, sin

from pedal_drill.enclosures.model import FaceDimensions
from pedal_drill.model import CircularHole, LineSegment, Point, Slot

_DEFAULT_CORNER_RADIUS = Decimal("5")
PREFERRED_CALIBRATION_LENGTHS_MM = (
    Decimal("100"),
    Decimal("90"),
    Decimal("80"),
    Decimal("70"),
    Decimal("60"),
    Decimal("50"),
    Decimal("40"),
    Decimal("30"),
    Decimal("20"),
)


class CalibrationOrientation(Enum):
    """The axis along which a calibration reference is drawn."""

    HORIZONTAL = auto()
    VERTICAL = auto()


@dataclass(frozen=True, slots=True)
class Rectangle:
    """An axis-aligned rectangle in the application's millimetre base unit."""

    x: Decimal
    y: Decimal
    width: Decimal
    height: Decimal

    def exceeded_boundaries(
        self, container: Rectangle, tolerance: Decimal
    ) -> tuple[str, ...]:
        """Return the named container boundaries crossed beyond *tolerance*."""

        exceeded: list[str] = []
        if self.x < container.x - tolerance:
            exceeded.append("left")
        if self.x + self.width > container.x + container.width + tolerance:
            exceeded.append("right")
        if self.y < container.y - tolerance:
            exceeded.append("bottom")
        if self.y + self.height > container.y + container.height + tolerance:
            exceeded.append("top")
        return tuple(exceeded)


@dataclass(frozen=True, slots=True)
class Capsule:
    """A rotated rounded rectangle, expressed in millimetres and degrees."""

    center: Point
    length: Decimal
    width: Decimal
    angle_degrees: Decimal

    @property
    def corner_radius(self) -> Decimal:
        """Return the radius that makes the short ends semicircular."""

        return self.width / 2


@dataclass(frozen=True, slots=True)
class CalibrationLine:
    """A dimensioned reference line positioned in a page gutter."""

    start: Point
    end: Point
    orientation: CalibrationOrientation

    @property
    def length(self) -> Decimal:
        """Return the line length in millimetres."""

        return abs(self.end.x - self.start.x) + abs(self.end.y - self.start.y)


def face_outline(
    dimensions: FaceDimensions, margin: Decimal, bottom_margin: Decimal | None = None
) -> Rectangle:
    """Return the face outline rectangle positioned inside a page margin."""

    return Rectangle(
        x=margin,
        y=bottom_margin if bottom_margin is not None else margin,
        width=dimensions.width,
        height=dimensions.height,
    )


def face_bounds(dimensions: FaceDimensions) -> Rectangle:
    """Return a face's coordinate bounds, with its Tayda origin at the centre."""

    return Rectangle(
        x=-(dimensions.width / 2),
        y=-(dimensions.height / 2),
        width=dimensions.width,
        height=dimensions.height,
    )


def face_corner_radius(dimensions: FaceDimensions) -> Decimal:
    """Return a conservative rounded-corner radius for a face outline."""

    return min(_DEFAULT_CORNER_RADIUS, dimensions.width / 4, dimensions.height / 4)


def face_point(
    point: Point,
    dimensions: FaceDimensions,
    margin: Decimal,
    bottom_margin: Decimal | None = None,
) -> Point:
    """Translate a centre-origin face point to a page point in millimetres."""

    return Point(
        x=margin + (dimensions.width / 2) + point.x,
        y=(bottom_margin if bottom_margin is not None else margin)
        + (dimensions.height / 2)
        + point.y,
    )


def capsule_for_slot(
    slot: Slot,
    dimensions: FaceDimensions,
    margin: Decimal,
    bottom_margin: Decimal | None = None,
) -> Capsule:
    """Translate a centre-origin slot to a page-positioned capsule."""

    return Capsule(
        center=face_point(slot.center, dimensions, margin, bottom_margin),
        length=slot.length,
        width=slot.width,
        angle_degrees=slot.angle_degrees,
    )


def circle_bounds(hole: CircularHole) -> Rectangle:
    """Return the complete circular-hole bounds in face coordinates."""

    radius = hole.diameter / 2
    return Rectangle(
        x=hole.center.x - radius,
        y=hole.center.y - radius,
        width=hole.diameter,
        height=hole.diameter,
    )


def capsule_bounds(capsule: Capsule) -> Rectangle:
    """Return tight axis-aligned bounds for a rotated capsule."""

    angle = radians(float(capsule.angle_degrees))
    radius = capsule.width / 2
    half_centerline = (capsule.length - capsule.width) / 2
    horizontal_extent = Decimal(str(abs(cos(angle)))) * half_centerline + radius
    vertical_extent = Decimal(str(abs(sin(angle)))) * half_centerline + radius
    return Rectangle(
        x=capsule.center.x - horizontal_extent,
        y=capsule.center.y - vertical_extent,
        width=horizontal_extent * 2,
        height=vertical_extent * 2,
    )


def line_bounds(line: LineSegment) -> Rectangle:
    """Return the bounds of a construction line in face coordinates."""

    return Rectangle(
        x=min(line.start.x, line.end.x),
        y=min(line.start.y, line.end.y),
        width=abs(line.end.x - line.start.x),
        height=abs(line.end.y - line.start.y),
    )


def select_calibration_length(available: Decimal) -> Decimal | None:
    """Select the largest preferred metric calibration length that fits."""

    return next(
        (
            length
            for length in PREFERRED_CALIBRATION_LENGTHS_MM
            if length <= available
        ),
        None,
    )


def calibration_lines(
    dimensions: FaceDimensions,
    margin: Decimal,
    bottom_margin: Decimal | None = None,
) -> tuple[CalibrationLine, CalibrationLine]:
    """Return horizontal and vertical gutter calibration lines for a face page."""

    horizontal_length = select_calibration_length(dimensions.width)
    vertical_length = select_calibration_length(dimensions.height)
    if horizontal_length is None or vertical_length is None:
        raise ValueError(
            "The enclosure face is too small for a 20 mm calibration line."
        )

    page_width = dimensions.width + (margin * 2)
    page_height = dimensions.height + margin + (
        bottom_margin if bottom_margin is not None else margin
    )
    return (
        CalibrationLine(
            start=Point((page_width - horizontal_length) / 2, margin / 2),
            end=Point((page_width + horizontal_length) / 2, margin / 2),
            orientation=CalibrationOrientation.HORIZONTAL,
        ),
        CalibrationLine(
            start=Point(margin / 2, (page_height - vertical_length) / 2),
            end=Point(margin / 2, (page_height + vertical_length) / 2),
            orientation=CalibrationOrientation.VERTICAL,
        ),
    )
