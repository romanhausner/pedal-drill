"""Renderer-independent normalization of drill features for enclosure overviews."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import atan2, degrees, hypot

from pedal_drill.geometry import Capsule
from pedal_drill.model import CircularHole, DrillTemplate, Face, LineSegment, Point

_GEOMETRY_TOLERANCE_MM = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class OverviewCircle:
    """An ordinary circular feature in a face's local coordinate system."""

    center: Point
    diameter: Decimal


@dataclass(frozen=True, slots=True)
class OverviewCapsule:
    """A single clean capsule outline in a face's local coordinate system."""

    capsule: Capsule


@dataclass(frozen=True, slots=True)
class OverviewArc:
    """A directed circular arc expressed in a face's local coordinates."""

    center: Point
    radius: Decimal
    start: Point
    end: Point
    start_angle_degrees: Decimal
    sweep_degrees: Decimal


@dataclass(frozen=True, slots=True)
class OverviewCompoundOutline:
    """A closed Tayda compound contour with source and normalized boundaries."""

    source_first_side: OverviewLine
    source_second_side: OverviewLine
    first_side: OverviewLine
    second_side: OverviewLine
    first_end_arc: OverviewArc
    second_end_arc: OverviewArc

    @property
    def is_closed(self) -> bool:
        """Return whether the final arc returns to the initial boundary point."""

        return self.first_end_arc.end == self.first_side.start


@dataclass(frozen=True, slots=True)
class OverviewLine:
    """An unconsumed construction line in a face's local coordinate system."""

    start: Point
    end: Point


OverviewFeature = (
    OverviewCircle | OverviewCapsule | OverviewCompoundOutline | OverviewLine
)


def overview_features(
    template: DrillTemplate, face: Face
) -> tuple[OverviewFeature, ...]:
    """Normalize source features for a reduced-scale enclosure overview.

    Tayda can encode elongated capsule shapes as two equal circular holes and
    two tangent construction lines.  This function merges only those complete,
    unambiguous compounds; all other source features remain independent.
    """

    holes = template.holes_on(face)
    lines = tuple(line for line in template.lines if line.face is face)
    consumed_holes: set[int] = set()
    consumed_lines: set[int] = set()
    compounds: list[OverviewCompoundOutline] = []

    for first_index, first in enumerate(holes):
        if first_index in consumed_holes:
            continue
        match = _capsule_compound_for_hole(
            first_index,
            holes,
            lines,
            consumed_holes,
            consumed_lines,
        )
        if match is None:
            continue
        second_index, line_indexes, compound = match
        consumed_holes.update((first_index, second_index))
        consumed_lines.update(line_indexes)
        compounds.append(compound)

    standalone_slots = tuple(
        OverviewCapsule(
            Capsule(slot.center, slot.length, slot.width, slot.angle_degrees)
        )
        for slot in template.slots
        if slot.face is face
    )
    circles = tuple(
        OverviewCircle(hole.center, hole.diameter)
        for index, hole in enumerate(holes)
        if index not in consumed_holes
    )
    remaining_lines = tuple(
        OverviewLine(line.start, line.end)
        for index, line in enumerate(lines)
        if index not in consumed_lines
    )
    return tuple(compounds) + standalone_slots + circles + remaining_lines


def _capsule_compound_for_hole(
    first_index: int,
    holes: tuple[CircularHole, ...],
    lines: tuple[LineSegment, ...],
    consumed_holes: set[int],
    consumed_lines: set[int],
) -> tuple[int, tuple[int, int], OverviewCompoundOutline] | None:
    """Return one unambiguous imported-boundary compound for *first_index*."""

    first = holes[first_index]
    for second_index, second in enumerate(holes[first_index + 1 :], first_index + 1):
        if second_index in consumed_holes:
            continue
        if second.diameter != first.diameter:
            continue
        if _distance(first.center, second.center) <= first.diameter:
            continue
        candidates = [
            index
            for index, line in enumerate(lines)
            if index not in consumed_lines
            and _connects_hole_pair(line, first, second)
        ]
        pair = _opposite_tangent_pair(candidates, lines, first.center, second.center)
        if pair is None:
            continue
        return (
            second_index,
            pair,
            _compound_outline(first, second, lines[pair[0]], lines[pair[1]]),
        )
    return None


def _connects_hole_pair(
    line: LineSegment,
    first: CircularHole,
    second: CircularHole,
) -> bool:
    """Return whether one imported line connects the two endpoint circles."""

    radius = first.diameter / 2
    endpoints_match = (
        _near(_distance(line.start, first.center), radius)
        and _near(_distance(line.end, second.center), radius)
    ) or (
        _near(_distance(line.start, second.center), radius)
        and _near(_distance(line.end, first.center), radius)
    )
    return endpoints_match


def _opposite_tangent_pair(
    candidates: list[int],
    lines: tuple[LineSegment, ...],
    first_center: Point,
    second_center: Point,
) -> tuple[int, int] | None:
    """Choose two connections lying on opposite sides of the centreline."""

    direction_x = second_center.x - first_center.x
    direction_y = second_center.y - first_center.y
    midpoint = Point(
        (first_center.x + second_center.x) / 2,
        (first_center.y + second_center.y) / 2,
    )
    positive: list[int] = []
    negative: list[int] = []
    for index in candidates:
        line = lines[index]
        line_midpoint = Point(
            (line.start.x + line.end.x) / 2,
            (line.start.y + line.end.y) / 2,
        )
        side = direction_x * (line_midpoint.y - midpoint.y) - direction_y * (
            line_midpoint.x - midpoint.x
        )
        if side > _GEOMETRY_TOLERANCE_MM:
            positive.append(index)
        elif side < -_GEOMETRY_TOLERANCE_MM:
            negative.append(index)
    if not positive or not negative:
        return None
    return positive[0], negative[0]


def _compound_outline(
    first: CircularHole,
    second: CircularHole,
    first_line: LineSegment,
    second_line: LineSegment,
) -> OverviewCompoundOutline:
    """Build an outline from imported sides and the exterior arcs they imply."""

    source_first_side, source_second_side = _ordered_sides(
        first_line,
        second_line,
        first,
        second,
    )
    first_radius = first.diameter / 2
    second_radius = second.diameter / 2
    first_side_start = _project_to_circle(
        source_first_side.start,
        first.center,
        first_radius,
    )
    second_side_start = _project_to_circle(
        source_second_side.start,
        first.center,
        first_radius,
    )
    first_side_end = _project_to_circle(
        source_first_side.end,
        second.center,
        second_radius,
    )
    second_side_end = _project_to_circle(
        source_second_side.end,
        second.center,
        second_radius,
    )
    outline = OverviewCompoundOutline(
        source_first_side=source_first_side,
        source_second_side=source_second_side,
        first_side=OverviewLine(first_side_start, first_side_end),
        second_side=OverviewLine(second_side_start, second_side_end),
        first_end_arc=_exterior_arc(
            center=first.center,
            radius=first_radius,
            start=second_side_start,
            end=first_side_start,
            away_from=second.center,
        ),
        second_end_arc=_exterior_arc(
            center=second.center,
            radius=second_radius,
            start=first_side_end,
            end=second_side_end,
            away_from=first.center,
        ),
    )
    _validate_compound_outline(outline)
    return outline


def _ordered_sides(
    first_line: LineSegment,
    second_line: LineSegment,
    first: CircularHole,
    second: CircularHole,
) -> tuple[OverviewLine, OverviewLine]:
    """Orient and order imported sides consistently from the near to far end."""

    candidates = (
        _orient_from_first_to_second(first_line, first, second),
        _orient_from_first_to_second(second_line, first, second),
    )
    direction_x = second.center.x - first.center.x
    direction_y = second.center.y - first.center.y
    midpoint = Point(
        (first.center.x + second.center.x) / 2,
        (first.center.y + second.center.y) / 2,
    )

    def side(line: OverviewLine) -> Decimal:
        line_midpoint = Point(
            (line.start.x + line.end.x) / 2,
            (line.start.y + line.end.y) / 2,
        )
        return direction_x * (line_midpoint.y - midpoint.y) - direction_y * (
            line_midpoint.x - midpoint.x
        )

    ordered = sorted(candidates, key=side, reverse=True)
    return ordered[0], ordered[1]


def _validate_compound_outline(outline: OverviewCompoundOutline) -> None:
    """Reject a malformed contour before any renderer can draw an interior edge."""

    if not outline.is_closed:
        raise ValueError("A compound overview outline must return to its start.")
    if outline.first_side.end != outline.second_end_arc.start:
        raise ValueError("The first compound side must meet the far exterior arc.")
    if outline.second_end_arc.end != outline.second_side.end:
        raise ValueError("The far exterior arc must meet the second compound side.")
    if outline.second_side.start != outline.first_end_arc.start:
        raise ValueError("The second compound side must meet the near exterior arc.")
    if _segments_intersect(outline.first_side, outline.second_side):
        raise ValueError("Compound overview boundary lines must not intersect.")
    if _arc_faces_inward(outline.first_end_arc, outline.second_end_arc.center):
        raise ValueError("The near compound arc must face away from the far endpoint.")
    if _arc_faces_inward(outline.second_end_arc, outline.first_end_arc.center):
        raise ValueError("The far compound arc must face away from the near endpoint.")


def _segments_intersect(first: OverviewLine, second: OverviewLine) -> bool:
    """Return whether two separate boundary segments cross in their interiors."""

    def orientation(start: Point, end: Point, point: Point) -> Decimal:
        return (end.x - start.x) * (point.y - start.y) - (end.y - start.y) * (
            point.x - start.x
        )

    first_start = orientation(first.start, first.end, second.start)
    first_end = orientation(first.start, first.end, second.end)
    second_start = orientation(second.start, second.end, first.start)
    second_end = orientation(second.start, second.end, first.end)
    return (first_start * first_end < 0) and (second_start * second_end < 0)


def _arc_faces_inward(arc: OverviewArc, opposite_center: Point) -> bool:
    """Return whether an arc midpoint points toward, rather than away from, the peer."""

    midpoint_angle = _arc_midpoint(arc.start_angle_degrees, arc.sweep_degrees)
    away_angle = _angle_from(
        arc.center,
        Point(
            (arc.center.x * 2) - opposite_center.x,
            (arc.center.y * 2) - opposite_center.y,
        ),
    )
    toward_angle = _angle_from(arc.center, opposite_center)
    return _angular_distance(midpoint_angle, toward_angle) < _angular_distance(
        midpoint_angle,
        away_angle,
    )


def _orient_from_first_to_second(
    line: LineSegment, first: CircularHole, second: CircularHole
) -> OverviewLine:
    """Orient an imported side from the first endpoint circle to the second."""

    if _distance(line.start, first.center) <= _distance(line.end, first.center):
        return OverviewLine(line.start, line.end)
    return OverviewLine(line.end, line.start)


def _project_to_circle(point: Point, center: Point, radius: Decimal) -> Point:
    """Project a rounded source endpoint radially onto its endpoint circle."""

    distance = _distance(point, center)
    if distance == 0:
        raise ValueError("A compound-line endpoint must not equal its hole centre.")
    factor = radius / distance
    return Point(
        center.x + (point.x - center.x) * factor,
        center.y + (point.y - center.y) * factor,
    )


def _exterior_arc(
    *,
    center: Point,
    radius: Decimal,
    start: Point,
    end: Point,
    away_from: Point,
) -> OverviewArc:
    """Choose the directed circle arc that faces away from the opposite centre."""

    start_angle = _angle_from(center, start)
    end_angle = _angle_from(center, end)
    away_angle = _angle_from(
        center,
        Point((center.x * 2) - away_from.x, (center.y * 2) - away_from.y),
    )
    counterclockwise_sweep = (end_angle - start_angle) % Decimal("360")
    clockwise_sweep = counterclockwise_sweep - Decimal("360")
    counterclockwise_distance = _angular_distance(
        _arc_midpoint(start_angle, counterclockwise_sweep), away_angle
    )
    clockwise_distance = _angular_distance(
        _arc_midpoint(start_angle, clockwise_sweep), away_angle
    )
    sweep = (
        counterclockwise_sweep
        if counterclockwise_distance <= clockwise_distance
        else clockwise_sweep
    )
    return OverviewArc(center, radius, start, end, start_angle, sweep)


def _angle_from(center: Point, point: Point) -> Decimal:
    """Return a normalized polar angle from *center* to *point* in degrees."""

    return _normalize_angle(
        Decimal(
            str(degrees(atan2(float(point.y - center.y), float(point.x - center.x))))
        )
    )


def _arc_midpoint(start: Decimal, sweep: Decimal) -> Decimal:
    """Return the normalized polar angle halfway along a directed arc."""

    return _normalize_angle(start + (sweep / 2))


def _angular_distance(first: Decimal, second: Decimal) -> Decimal:
    """Return the shortest distance between two normalized angles in degrees."""

    return abs(
        _normalize_angle(first - second + Decimal("180")) - Decimal("180")
    )


def _normalize_angle(angle: Decimal) -> Decimal:
    """Normalize an angle to the half-open range from 0 to 360 degrees."""

    normalized = angle % Decimal("360")
    return normalized + Decimal("360") if normalized < 0 else normalized


def _distance(first: Point, second: Point) -> Decimal:
    """Return the Euclidean distance in millimetres."""

    return Decimal(str(hypot(float(first.x - second.x), float(first.y - second.y))))


def _near(actual: Decimal, expected: Decimal) -> bool:
    """Compare imported coordinates with a small explicit millimetre tolerance."""

    return abs(actual - expected) <= _GEOMETRY_TOLERANCE_MM
