"""Focused tests for renderer-independent diameter-label placement."""

from decimal import Decimal
from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.geometry import Capsule, Polygon, face_polygon, point_in_polygon
from pedal_drill.label_placement import (
    CircleObstacle,
    LabelAlignment,
    LabelPosition,
    PlacedFeatureLabel,
    TextBounds,
    TextMetrics,
    label_candidates,
    place_feature_label,
    text_bounds_intersects_capsule,
    text_bounds_intersects_line,
    text_bounds_overlap,
)
from pedal_drill.model import CircularHole, DrillTemplate, Face, LineSegment, Point
from pedal_drill.renderers.pdf import ReportLabPdfRenderer

_METRICS = TextMetrics(Decimal("4"), Decimal("2"), Decimal("0"))


def _rectangle(width: str = "40", height: str = "40") -> Polygon:
    half_width = Decimal(width) / 2
    half_height = Decimal(height) / 2
    return Polygon(
        (
            Point(-half_width, half_height),
            Point(half_width, half_height),
            Point(half_width, -half_height),
            Point(-half_width, -half_height),
        )
    )


def _place(
    *,
    center: Point = Point(Decimal("0"), Decimal("0")),
    face: Polygon | None = None,
    circles: tuple[CircleObstacle, ...] | None = None,
    capsules: tuple[Capsule, ...] = (),
    lines: tuple[LineSegment, ...] = (),
    labels: tuple[PlacedFeatureLabel, ...] = (),
) -> PlacedFeatureLabel:
    own_circle = CircleObstacle(center, Decimal("2"))
    return place_feature_label(
        text="3.0",
        feature_center=center,
        feature_radius=Decimal("2"),
        face=face or _rectangle(),
        metrics=_METRICS,
        circles=circles or (own_circle,),
        capsules=capsules,
        lines=lines,
        placed_labels=labels,
        clearance=Decimal("0.5"),
        preferred_gap=Decimal("1"),
    )


def test_isolated_hole_keeps_a_centered_label_below() -> None:
    label = _place()

    assert label.position is LabelPosition.BELOW
    assert label.alignment is LabelAlignment.CENTER
    assert label.anchor.x == 0
    assert label.collision_penalty == 0


def test_line_crossing_default_position_moves_label_above() -> None:
    line = LineSegment(
        Face.A, Point(Decimal("-8"), Decimal("-4")), Point(Decimal("8"), Decimal("-4"))
    )

    label = _place(lines=(line,))

    assert label.position is LabelPosition.ABOVE
    assert not text_bounds_intersects_line(label.bounds.expanded(Decimal("0.5")), line)


def test_diagonal_capsule_crossing_default_position_is_avoided() -> None:
    capsule = Capsule(
        Point(Decimal("0"), Decimal("-4")),
        Decimal("12"),
        Decimal("2"),
        Decimal("35"),
    )

    label = _place(capsules=(capsule,))

    assert label.position is not LabelPosition.BELOW
    assert not text_bounds_intersects_capsule(
        label.bounds.expanded(Decimal("0.5")), capsule
    )


def test_nearby_hole_forces_an_alternative_position() -> None:
    own = CircleObstacle(Point(Decimal("0"), Decimal("0")), Decimal("2"))
    nearby = CircleObstacle(Point(Decimal("0"), Decimal("-4")), Decimal("2"))

    label = _place(circles=(own, nearby))

    assert label.position is LabelPosition.ABOVE


def test_previous_label_forces_an_alternative_position() -> None:
    below = label_candidates(
        Point(Decimal("0"), Decimal("0")),
        Decimal("2"),
        _METRICS,
        preferred_gap=Decimal("1"),
    )[0]
    previous = PlacedFeatureLabel(
        "3.0",
        below.position,
        below.anchor,
        below.alignment,
        below.bounds,
        Decimal("0"),
    )

    label = _place(labels=(previous,))

    assert label.position is LabelPosition.ABOVE
    assert not text_bounds_overlap(label.bounds, previous.bounds)


def test_labels_remain_inside_rectangular_and_trapezoidal_faces() -> None:
    rectangle_label = _place(
        center=Point(Decimal("0"), Decimal("-17")), face=_rectangle()
    )
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    trapezoid = face_polygon(enclosure.dimensions_for(Face.B), Face.B)
    trapezoid_label = _place(
        center=Point(Decimal("0"), Decimal("-12")), face=trapezoid
    )

    assert rectangle_label.position is LabelPosition.ABOVE
    assert all(
        point_in_polygon(corner, _rectangle())
        for corner in rectangle_label.bounds.corners
    )
    assert all(
        point_in_polygon(corner, trapezoid)
        for corner in trapezoid_label.bounds.corners
    )


def test_placement_is_deterministic() -> None:
    line = LineSegment(
        Face.A, Point(Decimal("-8"), Decimal("-4")), Point(Decimal("8"), Decimal("-4"))
    )

    results = tuple(_place(lines=(line,)) for _ in range(10))

    assert len(set(results)) == 1


def test_candidate_alignment_matches_direction() -> None:
    candidates = label_candidates(
        Point(Decimal("0"), Decimal("0")),
        Decimal("2"),
        _METRICS,
        preferred_gap=Decimal("1"),
    )
    by_position = {candidate.position: candidate for candidate in candidates}

    assert by_position[LabelPosition.BELOW].alignment is LabelAlignment.CENTER
    assert by_position[LabelPosition.ABOVE].alignment is LabelAlignment.CENTER
    assert by_position[LabelPosition.RIGHT].alignment is LabelAlignment.LEFT
    assert by_position[LabelPosition.LOWER_RIGHT].alignment is LabelAlignment.LEFT
    assert by_position[LabelPosition.LEFT].alignment is LabelAlignment.RIGHT
    assert by_position[LabelPosition.UPPER_LEFT].alignment is LabelAlignment.RIGHT


def test_lowest_penalty_candidate_is_used_when_none_is_clear() -> None:
    tiny_face = _rectangle("4", "4")

    label = _place(face=tiny_face)

    assert label.position is LabelPosition.BELOW
    assert label.collision_penalty > 0


def test_dense_tayda_diagonal_geometry_places_all_available_labels_cleanly() -> None:
    lower_centers = tuple(
        Point(Decimal(x), Decimal("50.229"))
        for x in ("-17.027", "-9.994", "-2.964", "4.077", "11.1")
    )
    upper_centers = tuple(
        Point(Decimal(x), Decimal("67.215"))
        for x in ("-18.463", "-11.433", "-4.392", "2.631", "9.66")
    )
    holes = tuple(
        CircularHole(Face.A, center, Decimal("3.0"))
        for center in lower_centers + upper_centers
    )
    lines = tuple(
        line
        for lower, upper in zip(lower_centers, upper_centers, strict=True)
        for line in (
            LineSegment(
                Face.A,
                Point(upper.x - Decimal("1.34"), upper.y - Decimal("0.759")),
                Point(lower.x - Decimal("1.34"), lower.y - Decimal("0.67")),
            ),
            LineSegment(
                Face.A,
                Point(upper.x + Decimal("1.34"), upper.y + Decimal("0.67")),
                Point(lower.x + Decimal("1.34"), lower.y + Decimal("0.669")),
            ),
        )
    )
    template = DrillTemplate(holes=holes, lines=lines, source_format="test")
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    renderer = ReportLabPdfRenderer()
    labels = renderer._place_hole_labels(
        template, enclosure.dimensions_for(Face.A), Face.A
    )
    assert all(label.collision_penalty == 0 for label in labels)
    for index, label in enumerate(labels):
        safe = label.bounds.expanded(Decimal("0.5"))
        assert not any(text_bounds_intersects_line(safe, line) for line in lines)
        assert not any(
            text_bounds_overlap(safe, previous.bounds)
            for previous in labels[:index]
        )
    assert any(label.position is not LabelPosition.BELOW for label in labels)


def test_reportlab_metrics_use_the_actual_string_width() -> None:
    renderer = ReportLabPdfRenderer()

    assert renderer._text_metrics("12.0").width > renderer._text_metrics("3.0").width


def test_text_bounds_are_plain_face_local_geometry() -> None:
    bounds = TextBounds(Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"))

    assert bounds.expanded(Decimal("0.5")) == TextBounds(
        Decimal("0.5"), Decimal("1.5"), Decimal("4"), Decimal("5")
    )
