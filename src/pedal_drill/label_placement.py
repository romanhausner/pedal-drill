"""Renderer-independent collision-aware placement of feature labels."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto
from typing import Sequence

from pedal_drill.geometry import (
    Capsule,
    Polygon,
    Rectangle,
    capsule_bounds,
    capsule_centerline_endpoints,
    point_in_polygon,
    point_to_segment_distance,
)
from pedal_drill.model import LineSegment, Point

_GEOMETRY_TOLERANCE = Decimal("0.000000001")
_FEATURE_PENALTY = Decimal("100")
_LINE_PENALTY = Decimal("250")
_LABEL_PENALTY = Decimal("10000")
_OUTSIDE_PENALTY = Decimal("10000")


class LabelAlignment(Enum):
    """Horizontal ReportLab-compatible text alignment."""

    CENTER = auto()
    LEFT = auto()
    RIGHT = auto()


class LabelPosition(Enum):
    """Stable preference order for positions around a circular feature."""

    BELOW = auto()
    ABOVE = auto()
    LOWER_RIGHT = auto()
    LOWER_LEFT = auto()
    RIGHT = auto()
    LEFT = auto()
    UPPER_RIGHT = auto()
    UPPER_LEFT = auto()


@dataclass(frozen=True, slots=True)
class TextMetrics:
    """Measured text extents in millimetres relative to its baseline."""

    width: Decimal
    ascent: Decimal
    descent: Decimal

    def __post_init__(self) -> None:
        if self.width <= 0 or self.ascent <= self.descent:
            raise ValueError("Text metrics must describe a positive text box.")

    @property
    def height(self) -> Decimal:
        """Return the complete ascent-to-descent height."""

        return self.ascent - self.descent


@dataclass(frozen=True, slots=True)
class TextBounds:
    """An axis-aligned text box in face-local millimetres."""

    x: Decimal
    y: Decimal
    width: Decimal
    height: Decimal

    @property
    def rectangle(self) -> Rectangle:
        """Return the shared geometry representation of this box."""

        return Rectangle(self.x, self.y, self.width, self.height)

    @property
    def corners(self) -> tuple[Point, Point, Point, Point]:
        """Return the four box corners in stable clockwise order."""

        return (
            Point(self.x, self.y + self.height),
            Point(self.x + self.width, self.y + self.height),
            Point(self.x + self.width, self.y),
            Point(self.x, self.y),
        )

    def expanded(self, clearance: Decimal) -> TextBounds:
        """Return a box enlarged equally in every direction."""

        return TextBounds(
            self.x - clearance,
            self.y - clearance,
            self.width + clearance * 2,
            self.height + clearance * 2,
        )


@dataclass(frozen=True, slots=True)
class CircleObstacle:
    """A circular drill symbol that labels must avoid."""

    center: Point
    radius: Decimal


@dataclass(frozen=True, slots=True)
class LabelCandidate:
    """One nearby anchor and its exact measured text box."""

    position: LabelPosition
    anchor: Point
    alignment: LabelAlignment
    bounds: TextBounds


@dataclass(frozen=True, slots=True)
class PlacedFeatureLabel:
    """The deterministic result of feature-label placement."""

    text: str
    position: LabelPosition
    anchor: Point
    alignment: LabelAlignment
    bounds: TextBounds
    collision_penalty: Decimal


def place_feature_label(
    *,
    text: str,
    feature_center: Point,
    feature_radius: Decimal,
    face: Polygon,
    metrics: TextMetrics,
    circles: Sequence[CircleObstacle] = (),
    capsules: Sequence[Capsule] = (),
    lines: Sequence[LineSegment] = (),
    placed_labels: Sequence[PlacedFeatureLabel] = (),
    clearance: Decimal = Decimal("0.5"),
    preferred_gap: Decimal = Decimal("1"),
) -> PlacedFeatureLabel:
    """Choose the first collision-free nearby label, or the least bad one.

    Candidate order is fixed by :class:`LabelPosition`; callers should likewise
    pass features and already placed labels in source order.  This makes dense
    layouts reproducible across runs and Python implementations.
    """

    if feature_radius <= 0:
        raise ValueError("A labelled feature radius must be greater than zero.")
    if clearance < 0 or preferred_gap < 0:
        raise ValueError("Label clearance and gap cannot be negative.")

    candidates = label_candidates(
        feature_center,
        feature_radius,
        metrics,
        preferred_gap=preferred_gap,
    )
    scored: list[tuple[Decimal, int, LabelCandidate]] = []
    for rank, candidate in enumerate(candidates):
        penalty = _collision_penalty(
            candidate.bounds,
            face=face,
            circles=circles,
            capsules=capsules,
            lines=lines,
            placed_labels=placed_labels,
            clearance=clearance,
        )
        if penalty == 0:
            return _placed_label(text, candidate, penalty)
        scored.append((penalty, rank, candidate))

    penalty, _, candidate = min(scored, key=lambda item: (item[0], item[1]))
    return _placed_label(text, candidate, penalty)


def label_candidates(
    center: Point,
    radius: Decimal,
    metrics: TextMetrics,
    *,
    preferred_gap: Decimal,
) -> tuple[LabelCandidate, ...]:
    """Return all candidate text boxes in their documented preference order."""

    below_baseline = center.y - radius - preferred_gap - metrics.ascent
    above_baseline = center.y + radius + preferred_gap - metrics.descent
    middle_baseline = center.y - (metrics.ascent + metrics.descent) / 2
    right_x = center.x + radius + preferred_gap
    left_x = center.x - radius - preferred_gap
    specifications = (
        (LabelPosition.BELOW, Point(center.x, below_baseline), LabelAlignment.CENTER),
        (LabelPosition.ABOVE, Point(center.x, above_baseline), LabelAlignment.CENTER),
        (
            LabelPosition.LOWER_RIGHT,
            Point(right_x, below_baseline),
            LabelAlignment.LEFT,
        ),
        (LabelPosition.LOWER_LEFT, Point(left_x, below_baseline), LabelAlignment.RIGHT),
        (LabelPosition.RIGHT, Point(right_x, middle_baseline), LabelAlignment.LEFT),
        (LabelPosition.LEFT, Point(left_x, middle_baseline), LabelAlignment.RIGHT),
        (
            LabelPosition.UPPER_RIGHT,
            Point(right_x, above_baseline),
            LabelAlignment.LEFT,
        ),
        (LabelPosition.UPPER_LEFT, Point(left_x, above_baseline), LabelAlignment.RIGHT),
    )
    return tuple(
        LabelCandidate(
            position,
            anchor,
            alignment,
            _text_bounds(anchor, alignment, metrics),
        )
        for position, anchor, alignment in specifications
    )


def text_bounds_intersects_line(bounds: TextBounds, line: LineSegment) -> bool:
    """Return whether a line touches or crosses a text box."""

    return _segment_intersects_rectangle(line.start, line.end, bounds)


def text_bounds_intersects_circle(
    bounds: TextBounds, circle: CircleObstacle
) -> bool:
    """Return whether a text box penetrates a circular obstacle."""

    return _point_to_rectangle_distance(circle.center, bounds) < (
        circle.radius - _GEOMETRY_TOLERANCE
    )


def text_bounds_intersects_capsule(bounds: TextBounds, capsule: Capsule) -> bool:
    """Return whether a text box penetrates a capsule's swept-circle outline."""

    capsule_box = capsule_bounds(capsule)
    if not _rectangles_touch(bounds, _bounds_from_rectangle(capsule_box)):
        return False
    start, end = capsule_centerline_endpoints(capsule)
    distance = _segment_to_rectangle_distance(start, end, bounds)
    return distance < capsule.width / 2 - _GEOMETRY_TOLERANCE


def text_bounds_overlap(first: TextBounds, second: TextBounds) -> bool:
    """Return whether two text boxes have positive overlap area."""

    return _intersection_area(first, second) > _GEOMETRY_TOLERANCE


def _placed_label(
    text: str, candidate: LabelCandidate, penalty: Decimal
) -> PlacedFeatureLabel:
    return PlacedFeatureLabel(
        text=text,
        position=candidate.position,
        anchor=candidate.anchor,
        alignment=candidate.alignment,
        bounds=candidate.bounds,
        collision_penalty=penalty,
    )


def _text_bounds(
    anchor: Point, alignment: LabelAlignment, metrics: TextMetrics
) -> TextBounds:
    if alignment is LabelAlignment.CENTER:
        x = anchor.x - metrics.width / 2
    elif alignment is LabelAlignment.RIGHT:
        x = anchor.x - metrics.width
    else:
        x = anchor.x
    return TextBounds(x, anchor.y + metrics.descent, metrics.width, metrics.height)


def _collision_penalty(
    bounds: TextBounds,
    *,
    face: Polygon,
    circles: Sequence[CircleObstacle],
    capsules: Sequence[Capsule],
    lines: Sequence[LineSegment],
    placed_labels: Sequence[PlacedFeatureLabel],
    clearance: Decimal,
) -> Decimal:
    safe = bounds.expanded(clearance)
    penalty = Decimal("0")

    outside = sum(
        max(
            Decimal("0"),
            max(
                -_signed_edge_clearance(corner, start, end)
                for start, end in face.edges
            ),
        )
        for corner in safe.corners
        if not point_in_polygon(corner, face, _GEOMETRY_TOLERANCE)
    )
    if outside:
        penalty += _OUTSIDE_PENALTY * (Decimal("1") + outside)

    for circle in circles:
        distance = _point_to_rectangle_distance(circle.center, safe)
        penetration = circle.radius - distance
        if penetration > _GEOMETRY_TOLERANCE:
            penalty += _FEATURE_PENALTY * (Decimal("1") + penetration)

    for capsule in capsules:
        if text_bounds_intersects_capsule(safe, capsule):
            start, end = capsule_centerline_endpoints(capsule)
            penetration = capsule.width / 2 - _segment_to_rectangle_distance(
                start, end, safe
            )
            penalty += _FEATURE_PENALTY * (
                Decimal("1") + max(Decimal("0"), penetration)
            )

    for line in lines:
        if text_bounds_intersects_line(safe, line):
            penalty += _LINE_PENALTY

    for label in placed_labels:
        overlap = _intersection_area(safe, label.bounds)
        if overlap > _GEOMETRY_TOLERANCE:
            penalty += _LABEL_PENALTY * (Decimal("1") + overlap)
    return penalty


def _signed_edge_clearance(point: Point, start: Point, end: Point) -> Decimal:
    delta_x = end.x - start.x
    delta_y = end.y - start.y
    length = (delta_x * delta_x + delta_y * delta_y).sqrt()
    cross = delta_x * (point.y - start.y) - delta_y * (point.x - start.x)
    return -cross / length


def _point_to_rectangle_distance(point: Point, bounds: TextBounds) -> Decimal:
    maximum_x = bounds.x + bounds.width
    maximum_y = bounds.y + bounds.height
    closest_x = min(maximum_x, max(bounds.x, point.x))
    closest_y = min(maximum_y, max(bounds.y, point.y))
    return ((point.x - closest_x) ** 2 + (point.y - closest_y) ** 2).sqrt()


def _segment_to_rectangle_distance(
    start: Point, end: Point, bounds: TextBounds
) -> Decimal:
    if _segment_intersects_rectangle(start, end, bounds):
        return Decimal("0")
    return min(
        _point_to_rectangle_distance(start, bounds),
        _point_to_rectangle_distance(end, bounds),
        *(point_to_segment_distance(corner, start, end) for corner in bounds.corners),
    )


def _segment_intersects_rectangle(
    start: Point, end: Point, bounds: TextBounds
) -> bool:
    if _point_inside_rectangle(start, bounds) or _point_inside_rectangle(end, bounds):
        return True
    corners = bounds.corners
    edges = tuple(
        (corner, corners[(index + 1) % len(corners)])
        for index, corner in enumerate(corners)
    )
    return any(
        _segments_intersect(start, end, edge_start, edge_end)
        for edge_start, edge_end in edges
    )


def _point_inside_rectangle(point: Point, bounds: TextBounds) -> bool:
    return (
        bounds.x - _GEOMETRY_TOLERANCE
        <= point.x
        <= bounds.x + bounds.width + _GEOMETRY_TOLERANCE
        and bounds.y - _GEOMETRY_TOLERANCE
        <= point.y
        <= bounds.y + bounds.height + _GEOMETRY_TOLERANCE
    )


def _segments_intersect(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> bool:
    def orientation(start: Point, end: Point, point: Point) -> Decimal:
        return (end.x - start.x) * (point.y - start.y) - (
            end.y - start.y
        ) * (point.x - start.x)

    values = (
        orientation(first_start, first_end, second_start),
        orientation(first_start, first_end, second_end),
        orientation(second_start, second_end, first_start),
        orientation(second_start, second_end, first_end),
    )
    first_crosses = values[0] * values[1] <= _GEOMETRY_TOLERANCE
    second_crosses = values[2] * values[3] <= _GEOMETRY_TOLERANCE
    if not (first_crosses and second_crosses):
        return False
    return _rectangles_touch(
        _segment_bounds(first_start, first_end),
        _segment_bounds(second_start, second_end),
    )


def _segment_bounds(start: Point, end: Point) -> TextBounds:
    return TextBounds(
        min(start.x, end.x),
        min(start.y, end.y),
        abs(end.x - start.x),
        abs(end.y - start.y),
    )


def _bounds_from_rectangle(rectangle: Rectangle) -> TextBounds:
    return TextBounds(rectangle.x, rectangle.y, rectangle.width, rectangle.height)


def _rectangles_touch(first: TextBounds, second: TextBounds) -> bool:
    return not (
        first.x + first.width < second.x - _GEOMETRY_TOLERANCE
        or second.x + second.width < first.x - _GEOMETRY_TOLERANCE
        or first.y + first.height < second.y - _GEOMETRY_TOLERANCE
        or second.y + second.height < first.y - _GEOMETRY_TOLERANCE
    )


def _intersection_area(first: TextBounds, second: TextBounds) -> Decimal:
    width = max(
        Decimal("0"),
        min(first.x + first.width, second.x + second.width)
        - max(first.x, second.x),
    )
    height = max(
        Decimal("0"),
        min(first.y + first.height, second.y + second.height)
        - max(first.y, second.y),
    )
    return width * height
