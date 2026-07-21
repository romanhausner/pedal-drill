"""Unit-preserving geometry calculations shared by validation and renderers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto
from math import cos, radians, sin

from pedal_drill.enclosures.model import EnclosureDefinition, FaceDimensions
from pedal_drill.model import CircularHole, Face, LineSegment, Point, Slot

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
class CircularArc:
    """One circular arc in a renderer-independent closed contour."""

    center: Point
    radius: Decimal
    start_angle_degrees: Decimal
    sweep_degrees: Decimal


@dataclass(frozen=True, slots=True)
class CapsulePath:
    """The canonical local-coordinate path for a capsule.

    The path starts at ``start``, follows a straight side to
    ``first_side_end``, then alternates an end arc and the opposite straight
    side.  The final arc ends back at ``start``, so renderers can fill and
    stroke one identical closed contour.
    """

    start: Point
    first_side_end: Point
    first_end_arc: CircularArc
    second_side_end: Point
    second_end_arc: CircularArc

    @property
    def is_closed(self) -> bool:
        """Return whether the final circular arc terminates at ``start``."""

        end_angle = radians(
            float(
                self.second_end_arc.start_angle_degrees
                + self.second_end_arc.sweep_degrees
            )
        )
        end = Point(
            self.second_end_arc.center.x
            + Decimal(str(cos(end_angle))) * self.second_end_arc.radius,
            self.second_end_arc.center.y
            + Decimal(str(sin(end_angle))) * self.second_end_arc.radius,
        )
        tolerance = Decimal("0.000000001")
        return (
            abs(end.x - self.start.x) <= tolerance
            and abs(end.y - self.start.y) <= tolerance
        )


def capsule_path(capsule: Capsule) -> CapsulePath:
    """Return the single canonical capsule contour in local coordinates."""

    radius = capsule.corner_radius
    half_centerline = (capsule.length - capsule.width) / 2
    return CapsulePath(
        start=Point(half_centerline, radius),
        first_side_end=Point(-half_centerline, radius),
        first_end_arc=CircularArc(
            center=Point(-half_centerline, Decimal("0")),
            radius=radius,
            start_angle_degrees=Decimal("90"),
            sweep_degrees=Decimal("180"),
        ),
        second_side_end=Point(half_centerline, -radius),
        second_end_arc=CircularArc(
            center=Point(half_centerline, Decimal("0")),
            radius=radius,
            start_angle_degrees=Decimal("270"),
            sweep_degrees=Decimal("180"),
        ),
    )


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


@dataclass(frozen=True, slots=True)
class FaceTransform:
    """Transform centre-origin face coordinates into overview-page coordinates."""

    origin: Point
    dimensions: FaceDimensions
    scale: Decimal

    def point(self, point: Point) -> Point:
        """Return *point* translated and uniformly scaled onto the overview."""

        return Point(
            self.origin.x + ((self.dimensions.width / 2) + point.x) * self.scale,
            self.origin.y + ((self.dimensions.height / 2) + point.y) * self.scale,
        )


@dataclass(frozen=True, slots=True)
class OverviewFace:
    """A face's outline and local-coordinate transform in an unfolded overview."""

    face: Face
    bounds: Rectangle
    transform: FaceTransform


@dataclass(frozen=True, slots=True)
class EnclosureOverview:
    """Renderer-independent geometry for a uniformly scaled unfolded enclosure."""

    page_bounds: Rectangle
    net_bounds: Rectangle
    scale: Decimal
    faces: tuple[OverviewFace, ...]

    def face_for(self, face: Face) -> OverviewFace:
        """Return overview geometry for a particular enclosure face."""

        return next(item for item in self.faces if item.face is face)


def enclosure_overview_geometry(
    enclosure: EnclosureDefinition,
    *,
    scale: Decimal = Decimal("0.5"),
    margin: Decimal = Decimal("10"),
) -> EnclosureOverview:
    """Build an unfolded A--E enclosure net in page coordinates.

    Face A is the centre of the net.  Its adjacent faces share edges directly;
    the returned scale is deliberately uniform so this orientation aid never
    distorts the relationships in the enclosure definition.
    """

    if scale <= 0:
        raise ValueError("The overview scale must be greater than zero.")
    if margin <= 0:
        raise ValueError("The overview margin must be greater than zero.")

    dimensions = {face: enclosure.dimensions_for(face) for face in Face}
    a = dimensions[Face.A]
    b = dimensions[Face.B]
    c = dimensions[Face.C]
    d = dimensions[Face.D]
    e = dimensions[Face.E]
    unscaled = {
        Face.A: Rectangle(Decimal("0"), Decimal("0"), a.width, a.height),
        Face.B: Rectangle(Decimal("0"), a.height, b.width, b.height),
        Face.C: Rectangle(-c.width, Decimal("0"), c.width, c.height),
        Face.D: Rectangle(Decimal("0"), -d.height, d.width, d.height),
        Face.E: Rectangle(a.width, Decimal("0"), e.width, e.height),
    }
    min_x = min(bounds.x for bounds in unscaled.values())
    min_y = min(bounds.y for bounds in unscaled.values())
    max_x = max(bounds.x + bounds.width for bounds in unscaled.values())
    max_y = max(bounds.y + bounds.height for bounds in unscaled.values())
    net_bounds = Rectangle(min_x, min_y, max_x - min_x, max_y - min_y)
    page_bounds = Rectangle(
        Decimal("0"),
        Decimal("0"),
        net_bounds.width * scale + margin * 2,
        net_bounds.height * scale + margin * 2,
    )

    overview_faces: list[OverviewFace] = []
    for face in Face:
        bounds = unscaled[face]
        origin = Point(
            margin + (bounds.x - net_bounds.x) * scale,
            margin + (bounds.y - net_bounds.y) * scale,
        )
        overview_faces.append(
            OverviewFace(
                face=face,
                bounds=Rectangle(
                    origin.x,
                    origin.y,
                    bounds.width * scale,
                    bounds.height * scale,
                ),
                transform=FaceTransform(origin, dimensions[face], scale),
            )
        )

    return EnclosureOverview(
        page_bounds=page_bounds,
        net_bounds=net_bounds,
        scale=scale,
        faces=tuple(overview_faces),
    )


def transform_overview_capsule(
    feature: Slot | Capsule, overview_face: OverviewFace
) -> Capsule:
    """Return a slot or normalized capsule transformed into overview coordinates."""

    return Capsule(
        center=overview_face.transform.point(feature.center),
        length=feature.length * overview_face.transform.scale,
        width=feature.width * overview_face.transform.scale,
        angle_degrees=feature.angle_degrees,
    )


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
