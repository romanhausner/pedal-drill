"""Unit-preserving geometry calculations shared by validation and renderers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto
from math import acos, cos, pi, radians, sin, tan

from pedal_drill.enclosures.model import (
    EnclosureDefinition,
    FaceGeometry,
    TrapezoidFaceDimensions,
)
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
class Polygon:
    """A convex polygon with clockwise vertices in millimetres."""

    vertices: tuple[Point, ...]

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError("A polygon requires at least three vertices.")
        twice_area = sum(
            start.x * end.y - end.x * start.y
            for start, end in self.edges
        )
        if twice_area >= 0:
            raise ValueError("Polygon vertices must use clockwise winding.")

    @property
    def edges(self) -> tuple[tuple[Point, Point], ...]:
        """Return consecutive boundary segments, including the closing edge."""

        return tuple(
            (vertex, self.vertices[(index + 1) % len(self.vertices)])
            for index, vertex in enumerate(self.vertices)
        )

    @property
    def bounds(self) -> Rectangle:
        """Return the polygon's tight axis-aligned bounds."""

        minimum_x = min(vertex.x for vertex in self.vertices)
        maximum_x = max(vertex.x for vertex in self.vertices)
        minimum_y = min(vertex.y for vertex in self.vertices)
        maximum_y = max(vertex.y for vertex in self.vertices)
        return Rectangle(
            minimum_x,
            minimum_y,
            maximum_x - minimum_x,
            maximum_y - minimum_y,
        )


@dataclass(frozen=True, slots=True)
class RoundedCorner:
    """One renderer-independent cubic transition around a polygon corner."""

    start: Point
    control1: Point
    control2: Point
    end: Point


@dataclass(frozen=True, slots=True)
class RoundedPolygonPath:
    """A closed polygon contour made from alternating lines and cubic curves."""

    start: Point
    corners: tuple[RoundedCorner, ...]


def rounded_polygon_path(
    polygon: Polygon, radius: Decimal
) -> RoundedPolygonPath:
    """Return an inward-clamped rounded contour for a convex polygon.

    Tangent and Bézier control points remain on the polygon edges.  Because a
    Bézier curve stays within the convex hull of its control points, the
    resulting outline cannot extend outside the original face envelope.
    """

    if radius <= 0:
        raise ValueError("The rounded polygon radius must be greater than zero.")

    corner_data: list[tuple[Point, float, float, float, float]] = []
    offsets_per_mm: list[float] = []
    controls_per_mm: list[float] = []
    vertices = polygon.vertices
    for index, vertex in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % len(vertices)]
        previous_x, previous_y = _unit_direction(vertex, previous)
        following_x, following_y = _unit_direction(vertex, following)
        dot = max(
            -1.0,
            min(1.0, previous_x * following_x + previous_y * following_y),
        )
        interior_angle = acos(dot)
        offset_per_mm = 1.0 / tan(interior_angle / 2.0)
        control_per_mm = (4.0 / 3.0) * tan((pi - interior_angle) / 4.0)
        corner_data.append(
            (
                vertex,
                previous_x,
                previous_y,
                following_x,
                following_y,
            )
        )
        offsets_per_mm.append(offset_per_mm)
        controls_per_mm.append(control_per_mm)

    requested_radius = float(radius)
    radius_scale = 1.0
    for index, (start, end) in enumerate(polygon.edges):
        edge_length = float(
            ((end.x - start.x) ** 2 + (end.y - start.y) ** 2).sqrt()
        )
        combined_offset = requested_radius * (
            offsets_per_mm[index]
            + offsets_per_mm[(index + 1) % len(vertices)]
        )
        if combined_offset > 0:
            radius_scale = min(radius_scale, edge_length * 0.9 / combined_offset)

    effective_radius = requested_radius * radius_scale
    corners: list[RoundedCorner] = []
    for index, data in enumerate(corner_data):
        vertex, previous_x, previous_y, following_x, following_y = data
        offset = effective_radius * offsets_per_mm[index]
        control = effective_radius * controls_per_mm[index]
        tangent_start = _offset_point(vertex, previous_x, previous_y, offset)
        tangent_end = _offset_point(vertex, following_x, following_y, offset)
        corners.append(
            RoundedCorner(
                start=tangent_start,
                control1=_offset_point(
                    tangent_start, -previous_x, -previous_y, control
                ),
                control2=_offset_point(
                    tangent_end, -following_x, -following_y, control
                ),
                end=tangent_end,
            )
        )

    traversal = tuple(corners[1:] + corners[:1])
    return RoundedPolygonPath(start=corners[0].end, corners=traversal)


def _unit_direction(start: Point, end: Point) -> tuple[float, float]:
    delta_x = end.x - start.x
    delta_y = end.y - start.y
    length = (delta_x * delta_x + delta_y * delta_y).sqrt()
    if length == 0:
        raise ValueError("A rounded polygon cannot contain a zero-length edge.")
    return float(delta_x / length), float(delta_y / length)


def _offset_point(
    point: Point, direction_x: float, direction_y: float, distance: float
) -> Point:
    return Point(
        point.x + Decimal(str(direction_x * distance)),
        point.y + Decimal(str(direction_y * distance)),
    )


def trapezoid_outline_vertices(
    dimensions: TrapezoidFaceDimensions,
) -> tuple[Point, ...]:
    """Return the mandated clockwise vertices of a centred trapezoid."""

    half_height = dimensions.height / 2
    half_top = dimensions.top_width / 2
    half_bottom = dimensions.bottom_width / 2
    return (
        Point(-half_top, half_height),
        Point(half_top, half_height),
        Point(half_bottom, -half_height),
        Point(-half_bottom, -half_height),
    )


def face_outline_vertices(
    dimensions: FaceGeometry, face: Face | None = None
) -> tuple[Point, ...]:
    """Return clockwise vertices in the established local face orientation."""

    if isinstance(dimensions, TrapezoidFaceDimensions):
        turns = _detail_face_quarter_turns(face)
        return tuple(
            _quarter_turn(vertex, turns)
            for vertex in trapezoid_outline_vertices(dimensions)
        )
    half_height = dimensions.height / 2
    half_width = dimensions.width / 2
    return (
        Point(-half_width, half_height),
        Point(half_width, half_height),
        Point(half_width, -half_height),
        Point(-half_width, -half_height),
    )


def face_polygon(dimensions: FaceGeometry, face: Face | None = None) -> Polygon:
    """Return the common polygon representation of a face envelope."""

    return Polygon(face_outline_vertices(dimensions, face))


def translate_polygon(polygon: Polygon, offset: Point) -> Polygon:
    """Translate a polygon without changing its winding or dimensions."""

    return Polygon(
        tuple(
            Point(vertex.x + offset.x, vertex.y + offset.y)
            for vertex in polygon.vertices
        )
    )


def point_to_segment_distance(point: Point, start: Point, end: Point) -> Decimal:
    """Return the shortest Euclidean distance from a point to a segment."""

    delta_x = end.x - start.x
    delta_y = end.y - start.y
    length_squared = delta_x * delta_x + delta_y * delta_y
    if length_squared == 0:
        return ((point.x - start.x) ** 2 + (point.y - start.y) ** 2).sqrt()
    projection = (
        (point.x - start.x) * delta_x + (point.y - start.y) * delta_y
    ) / length_squared
    projection = min(Decimal("1"), max(Decimal("0"), projection))
    closest = Point(start.x + projection * delta_x, start.y + projection * delta_y)
    return ((point.x - closest.x) ** 2 + (point.y - closest.y) ** 2).sqrt()


def distance_to_polygon_edges(point: Point, polygon: Polygon) -> Decimal:
    """Return the minimum unsigned distance from a point to the outline."""

    return min(
        point_to_segment_distance(point, start, end)
        for start, end in polygon.edges
    )


def polygon_edge_clearances(point: Point, polygon: Polygon) -> tuple[Decimal, ...]:
    """Return signed inward distances to each clockwise polygon edge."""

    clearances: list[Decimal] = []
    for start, end in polygon.edges:
        delta_x = end.x - start.x
        delta_y = end.y - start.y
        edge_length = (delta_x * delta_x + delta_y * delta_y).sqrt()
        cross = delta_x * (point.y - start.y) - delta_y * (point.x - start.x)
        clearances.append(-cross / edge_length)
    return tuple(clearances)


def point_in_polygon(
    point: Point, polygon: Polygon, tolerance: Decimal = Decimal("0")
) -> bool:
    """Return whether a point is inside or tangent to a convex polygon."""

    return all(
        clearance >= -tolerance
        for clearance in polygon_edge_clearances(point, polygon)
    )


def polygon_contains_circle(
    polygon: Polygon,
    center: Point,
    radius: Decimal,
    tolerance: Decimal = Decimal("0"),
) -> bool:
    """Return whether a complete circle lies inside a convex polygon."""

    return all(
        clearance >= radius - tolerance
        for clearance in polygon_edge_clearances(center, polygon)
    )


def capsule_centerline_endpoints(capsule: Capsule) -> tuple[Point, Point]:
    """Return the centres of the two semicircular capsule ends."""

    half_centerline = (capsule.length - capsule.width) / 2
    angle = radians(float(capsule.angle_degrees))
    delta_x = Decimal(str(cos(angle))) * half_centerline
    delta_y = Decimal(str(sin(angle))) * half_centerline
    return (
        Point(capsule.center.x - delta_x, capsule.center.y - delta_y),
        Point(capsule.center.x + delta_x, capsule.center.y + delta_y),
    )


def polygon_contains_capsule(
    polygon: Polygon,
    capsule: Capsule,
    tolerance: Decimal = Decimal("0"),
) -> bool:
    """Return whether a complete rounded slot lies inside a convex polygon."""

    radius = capsule.width / 2
    return all(
        clearance >= radius - tolerance
        for endpoint in capsule_centerline_endpoints(capsule)
        for clearance in polygon_edge_clearances(endpoint, polygon)
    )


def polygon_contains_line(
    polygon: Polygon,
    start: Point,
    end: Point,
    tolerance: Decimal = Decimal("0"),
) -> bool:
    """Return whether a line segment lies inside a convex polygon."""

    return point_in_polygon(start, polygon, tolerance) and point_in_polygon(
        end, polygon, tolerance
    )


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
    dimensions: FaceGeometry
    scale: Decimal
    quarter_turns: int = 0
    local_bounds: Rectangle | None = None

    @property
    def _source_bounds(self) -> Rectangle:
        return self.local_bounds or face_polygon(self.dimensions).bounds

    @property
    def display_width(self) -> Decimal:
        """Return the unscaled width after the overview rotation."""

        bounds = self._source_bounds
        return bounds.height if self.quarter_turns % 2 else bounds.width

    @property
    def display_height(self) -> Decimal:
        """Return the unscaled height after the overview rotation."""

        bounds = self._source_bounds
        return bounds.width if self.quarter_turns % 2 else bounds.height

    def point(self, point: Point) -> Point:
        """Return *point* translated and uniformly scaled onto the overview."""

        rotated = _quarter_turn(point, self.quarter_turns)
        return Point(
            self.origin.x + ((self.display_width / 2) + rotated.x) * self.scale,
            self.origin.y + ((self.display_height / 2) + rotated.y) * self.scale,
        )

    def polygon(self, polygon: Polygon) -> Polygon:
        """Transform a local polygon into overview-page coordinates."""

        return Polygon(tuple(self.point(vertex) for vertex in polygon.vertices))


@dataclass(frozen=True, slots=True)
class OverviewFace:
    """A face's outline and local-coordinate transform in an unfolded overview."""

    face: Face
    bounds: Rectangle
    transform: FaceTransform
    outline: Polygon


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


@dataclass(frozen=True, slots=True)
class OverviewFaceLabelPlacement:
    """A measured horizontal label placed safely inside an overview face."""

    anchor: Point
    bounds: Rectangle
    safe_left: Decimal
    safe_right: Decimal


def overview_attachment_label_placement(
    overview_face: OverviewFace,
    *,
    text_width: Decimal,
    text_ascent: Decimal,
    text_descent: Decimal,
    corner_radius: Decimal,
    preferred_clearance: Decimal = Decimal("1"),
    minimum_clearance: Decimal = Decimal("0.4"),
) -> OverviewFaceLabelPlacement:
    """Place a B/D label beside its straight Face-A attachment edge.

    The actual rounded-contour tangent points define the usable horizontal
    span, so neither a trapezoid's wider outer edge nor its bounding box can
    accidentally put text into a corner transition.  The returned anchor is a
    centred ReportLab baseline in overview-page millimetres.
    """

    if overview_face.face not in (Face.B, Face.D):
        raise ValueError("Attachment-edge label placement supports only faces B and D.")
    if text_width <= 0 or text_ascent <= text_descent:
        raise ValueError("Overview label text metrics must define a positive box.")
    if minimum_clearance < 0 or preferred_clearance < minimum_clearance:
        raise ValueError("Overview label clearances are invalid.")

    attachment_y = (
        overview_face.bounds.y
        if overview_face.face is Face.B
        else overview_face.bounds.y + overview_face.bounds.height
    )
    contour = rounded_polygon_path(overview_face.outline, corner_radius)
    tangent_points = tuple(
        point
        for corner in contour.corners
        for point in (corner.start, corner.end)
        if abs(point.y - attachment_y) <= Decimal("0.000000001")
    )
    if len(tangent_points) != 2:
        raise ValueError("Could not identify the rounded attachment-edge span.")
    straight_left = min(point.x for point in tangent_points)
    straight_right = max(point.x for point in tangent_points)
    text_height = text_ascent - text_descent

    clearances = tuple(
        dict.fromkeys((preferred_clearance, minimum_clearance))
    )
    vertical_insets = (
        preferred_clearance,
        preferred_clearance + Decimal("1"),
    )
    for vertical_inset in vertical_insets:
        for horizontal_inset in clearances:
            safe_left = straight_left + horizontal_inset
            safe_right = straight_right - horizontal_inset
            if text_width > safe_right - safe_left:
                continue
            center_x = (safe_left + safe_right) / 2
            if overview_face.face is Face.B:
                box_y = attachment_y + vertical_inset
            else:
                box_y = attachment_y - vertical_inset - text_height
            bounds = Rectangle(
                center_x - text_width / 2,
                box_y,
                text_width,
                text_height,
            )
            if (
                bounds.x < overview_face.bounds.x
                or bounds.x + bounds.width
                > overview_face.bounds.x + overview_face.bounds.width
                or bounds.y < overview_face.bounds.y
                or bounds.y + bounds.height
                > overview_face.bounds.y + overview_face.bounds.height
            ):
                continue
            return OverviewFaceLabelPlacement(
                anchor=Point(center_x, box_y - text_descent),
                bounds=bounds,
                safe_left=safe_left,
                safe_right=safe_right,
            )
    raise ValueError("The overview face label does not fit its attachment edge.")


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

    dimensions, local_polygons, rotations, unscaled, net_bounds = (
        _unscaled_overview_layout(enclosure)
    )
    page_bounds = Rectangle(
        Decimal("0"),
        Decimal("0"),
        net_bounds.width * scale + margin * 2,
        net_bounds.height * scale + margin * 2,
    )
    return _positioned_overview(
        dimensions,
        local_polygons,
        rotations,
        unscaled,
        net_bounds,
        page_bounds=page_bounds,
        drawing_origin=Point(margin, margin),
        scale=scale,
    )


def fitted_enclosure_overview_geometry(
    enclosure: EnclosureDefinition,
    *,
    page_bounds: Rectangle,
    drawing_area: Rectangle,
    safety_factor: Decimal = Decimal("0.97"),
) -> EnclosureOverview:
    """Fit and centre an unfolded enclosure net in a fixed page drawing area.

    The scale is the largest uniform scale permitted by *drawing_area*, reduced
    only by the explicit safety factor.  Page chrome such as headers and footers
    therefore remains the renderer's responsibility while the fitting math is
    reusable by other output formats.
    """

    if drawing_area.width <= 0 or drawing_area.height <= 0:
        raise ValueError("The overview drawing area must have positive dimensions.")
    if safety_factor <= 0 or safety_factor > 1:
        raise ValueError(
            "The overview safety factor must be greater than 0 and at most 1."
        )
    if (
        drawing_area.x < page_bounds.x
        or drawing_area.y < page_bounds.y
        or drawing_area.x + drawing_area.width
        > page_bounds.x + page_bounds.width
        or drawing_area.y + drawing_area.height
        > page_bounds.y + page_bounds.height
    ):
        raise ValueError("The overview drawing area must lie inside the page bounds.")

    dimensions, local_polygons, rotations, unscaled, net_bounds = (
        _unscaled_overview_layout(enclosure)
    )
    scale = min(
        drawing_area.width / net_bounds.width,
        drawing_area.height / net_bounds.height,
    ) * safety_factor
    scaled_width = net_bounds.width * scale
    scaled_height = net_bounds.height * scale
    drawing_origin = Point(
        drawing_area.x + (drawing_area.width - scaled_width) / 2,
        drawing_area.y + (drawing_area.height - scaled_height) / 2,
    )
    return _positioned_overview(
        dimensions,
        local_polygons,
        rotations,
        unscaled,
        net_bounds,
        page_bounds=page_bounds,
        drawing_origin=drawing_origin,
        scale=scale,
    )


def _unscaled_overview_layout(
    enclosure: EnclosureDefinition,
) -> tuple[
    dict[Face, FaceGeometry],
    dict[Face, Polygon],
    dict[Face, int],
    dict[Face, Rectangle],
    Rectangle,
]:
    """Return the established unfolded net before page fitting or scaling."""

    dimensions = {face: enclosure.dimensions_for(face) for face in Face}
    b = dimensions[Face.B]
    local_polygons = {
        face: face_polygon(dimensions[face], face) for face in Face
    }
    rotations = {
        Face.A: 0,
        Face.B: 2 if isinstance(b, TrapezoidFaceDimensions) else 0,
        Face.C: 0,
        Face.D: 0,
        Face.E: 0,
    }
    display = {
        face: _display_dimensions(local_polygons[face].bounds, rotations[face])
        for face in Face
    }
    a_width, a_height = display[Face.A]
    b_width, b_height = display[Face.B]
    c_width, c_height = display[Face.C]
    d_width, d_height = display[Face.D]
    e_width, e_height = display[Face.E]
    unscaled = {
        Face.A: Rectangle(Decimal("0"), Decimal("0"), a_width, a_height),
        Face.B: Rectangle(Decimal("0"), a_height, b_width, b_height),
        Face.C: Rectangle(-c_width, Decimal("0"), c_width, c_height),
        Face.D: Rectangle(Decimal("0"), -d_height, d_width, d_height),
        Face.E: Rectangle(a_width, Decimal("0"), e_width, e_height),
    }
    min_x = min(bounds.x for bounds in unscaled.values())
    min_y = min(bounds.y for bounds in unscaled.values())
    max_x = max(bounds.x + bounds.width for bounds in unscaled.values())
    max_y = max(bounds.y + bounds.height for bounds in unscaled.values())
    net_bounds = Rectangle(min_x, min_y, max_x - min_x, max_y - min_y)
    return dimensions, local_polygons, rotations, unscaled, net_bounds


def _positioned_overview(
    dimensions: dict[Face, FaceGeometry],
    local_polygons: dict[Face, Polygon],
    rotations: dict[Face, int],
    unscaled: dict[Face, Rectangle],
    net_bounds: Rectangle,
    *,
    page_bounds: Rectangle,
    drawing_origin: Point,
    scale: Decimal,
) -> EnclosureOverview:
    """Apply one uniform scale and page translation to an unfolded net."""

    overview_faces: list[OverviewFace] = []
    for face in Face:
        bounds = unscaled[face]
        origin = Point(
            drawing_origin.x + (bounds.x - net_bounds.x) * scale,
            drawing_origin.y + (bounds.y - net_bounds.y) * scale,
        )
        transform = FaceTransform(
            origin,
            dimensions[face],
            scale,
            rotations[face],
            local_polygons[face].bounds,
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
                transform=transform,
                outline=transform.polygon(local_polygons[face]),
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
        angle_degrees=(
            feature.angle_degrees
            + Decimal(overview_face.transform.quarter_turns * 90)
        ),
    )


def face_outline(
    dimensions: FaceGeometry, margin: Decimal, bottom_margin: Decimal | None = None
) -> Rectangle:
    """Return the face outline rectangle positioned inside a page margin."""

    return Rectangle(
        x=margin,
        y=bottom_margin if bottom_margin is not None else margin,
        width=dimensions.width,
        height=dimensions.height,
    )


def face_bounds(dimensions: FaceGeometry, face: Face | None = None) -> Rectangle:
    """Return a face's coordinate bounds, with its Tayda origin at the centre."""

    return face_polygon(dimensions, face).bounds


def face_corner_radius(dimensions: FaceGeometry) -> Decimal:
    """Return a conservative rounded-corner radius for a face outline."""

    return min(_DEFAULT_CORNER_RADIUS, dimensions.width / 4, dimensions.height / 4)


def face_point(
    point: Point,
    dimensions: FaceGeometry,
    margin: Decimal,
    bottom_margin: Decimal | None = None,
    face: Face | None = None,
) -> Point:
    """Translate a centre-origin face point to a page point in millimetres."""

    bounds = face_bounds(dimensions, face)
    return Point(
        x=margin + (bounds.width / 2) + point.x,
        y=(bottom_margin if bottom_margin is not None else margin)
        + (bounds.height / 2)
        + point.y,
    )


def capsule_for_slot(
    slot: Slot,
    dimensions: FaceGeometry,
    margin: Decimal,
    bottom_margin: Decimal | None = None,
) -> Capsule:
    """Translate a centre-origin slot to a page-positioned capsule."""

    return Capsule(
        center=face_point(
            slot.center,
            dimensions,
            margin,
            bottom_margin,
            slot.face,
        ),
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


def positioned_face_polygon(
    dimensions: FaceGeometry,
    margin: Decimal,
    bottom_margin: Decimal | None = None,
    face: Face | None = None,
) -> Polygon:
    """Translate a local face polygon to its detail-page position."""

    center = face_point(
        Point(Decimal("0"), Decimal("0")),
        dimensions,
        margin,
        bottom_margin,
        face,
    )
    return translate_polygon(face_polygon(dimensions, face), center)


def _quarter_turn(point: Point, quarter_turns: int) -> Point:
    turns = quarter_turns % 4
    if turns == 0:
        return point
    if turns == 1:
        return Point(-point.y, point.x)
    if turns == 2:
        return Point(-point.x, -point.y)
    return Point(point.y, -point.x)


def _display_dimensions(
    bounds: Rectangle, quarter_turns: int
) -> tuple[Decimal, Decimal]:
    if quarter_turns % 2:
        return bounds.height, bounds.width
    return bounds.width, bounds.height


def _detail_face_quarter_turns(face: Face | None) -> int:
    if face is Face.C:
        return 3
    if face is Face.E:
        return 1
    return 0


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
    dimensions: FaceGeometry,
    margin: Decimal,
    bottom_margin: Decimal | None = None,
    face: Face | None = None,
) -> tuple[CalibrationLine, CalibrationLine]:
    """Return horizontal and vertical gutter calibration lines for a face page."""

    bounds = face_bounds(dimensions, face)
    horizontal_length = select_calibration_length(bounds.width)
    vertical_length = select_calibration_length(bounds.height)
    if horizontal_length is None or vertical_length is None:
        raise ValueError(
            "The enclosure face is too small for a 20 mm calibration line."
        )

    page_width = bounds.width + (margin * 2)
    page_height = bounds.height + margin + (
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
