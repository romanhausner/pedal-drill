from decimal import Decimal

from pedal_drill.enclosures import TrapezoidFaceDimensions
from pedal_drill.geometry import (
    distance_to_polygon_edges,
    face_polygon,
    point_in_polygon,
    rounded_polygon_path,
    trapezoid_outline_vertices,
)
from pedal_drill.model import Face, Point


def test_trapezoid_vertices_are_clockwise_and_symmetrically_centred() -> None:
    dimensions = TrapezoidFaceDimensions(
        Decimal("80"), Decimal("100"), Decimal("40")
    )

    vertices = trapezoid_outline_vertices(dimensions)

    assert vertices == (
        Point(Decimal("-40"), Decimal("20")),
        Point(Decimal("40"), Decimal("20")),
        Point(Decimal("50"), Decimal("-20")),
        Point(Decimal("-50"), Decimal("-20")),
    )
    assert vertices[0].x == -vertices[1].x
    assert vertices[3].x == -vertices[2].x


def test_trapezoid_bounds_use_maximum_width_and_full_height() -> None:
    polygon = face_polygon(
        TrapezoidFaceDimensions(
            Decimal("80"), Decimal("100"), Decimal("40")
        )
    )

    assert polygon.bounds.x == Decimal("-50")
    assert polygon.bounds.y == Decimal("-20")
    assert polygon.bounds.width == Decimal("100")
    assert polygon.bounds.height == Decimal("40")
    assert distance_to_polygon_edges(Point(Decimal("0"), Decimal("0")), polygon) > 0


def test_long_side_faces_follow_existing_tayda_coordinate_orientation() -> None:
    dimensions = TrapezoidFaceDimensions(
        Decimal("143.36"), Decimal("145.20"), Decimal("35.20")
    )

    left = face_polygon(dimensions, Face.C)
    right = face_polygon(dimensions, Face.E)

    assert left.bounds.width == Decimal("35.20")
    assert left.bounds.height == Decimal("145.20")
    assert right.bounds == left.bounds
    # The narrow Face A edge is on the side adjacent to central Face A.
    assert left.vertices[0].x == Decimal("17.60")
    assert right.vertices[0].x == Decimal("-17.60")


def test_rounded_trapezoid_path_stays_inside_the_sharp_envelope() -> None:
    polygon = face_polygon(
        TrapezoidFaceDimensions(
            Decimal("119.36"), Decimal("121.20"), Decimal("35.20")
        ),
        Face.B,
    )

    contour = rounded_polygon_path(polygon, Decimal("5"))

    assert len(contour.corners) == 4
    path_points = (contour.start,) + tuple(
        point
        for corner in contour.corners
        for point in (corner.start, corner.control1, corner.control2, corner.end)
    )
    assert all(
        point_in_polygon(point, polygon, Decimal("0.000000000001"))
        for point in path_points
    )
    assert all(
        polygon.bounds.x <= point.x <= polygon.bounds.x + polygon.bounds.width
        and polygon.bounds.y <= point.y <= polygon.bounds.y + polygon.bounds.height
        for point in path_points
    )


def test_rounded_trapezoid_radius_is_clamped_for_short_edges() -> None:
    polygon = face_polygon(
        TrapezoidFaceDimensions(Decimal("4"), Decimal("6"), Decimal("3"))
    )

    contour = rounded_polygon_path(polygon, Decimal("5"))

    current = contour.start
    for corner in contour.corners:
        assert _distance(current, corner.start) > 0
        assert point_in_polygon(
            corner.control1, polygon, Decimal("0.000000000001")
        )
        assert point_in_polygon(
            corner.control2, polygon, Decimal("0.000000000001")
        )
        current = corner.end


def _distance(start: Point, end: Point) -> Decimal:
    return ((end.x - start.x) ** 2 + (end.y - start.y) ** 2).sqrt()
