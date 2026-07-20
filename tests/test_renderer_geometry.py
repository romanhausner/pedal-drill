from decimal import Decimal

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.model import Face, Point, Slot
from pedal_drill.renderers.geometry import capsule_for_slot, face_outline, face_point


def test_face_geometry_uses_the_definition_dimensions_and_page_margin() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)

    outline = face_outline(dimensions, Decimal("10"))
    center = face_point(Point(Decimal("0"), Decimal("0")), dimensions, Decimal("10"))

    assert outline.width == Decimal("121.20")
    assert outline.height == Decimal("145.20")
    assert (outline.x, outline.y) == (Decimal("10"), Decimal("10"))
    assert center == Point(Decimal("70.60"), Decimal("82.60"))


def test_slot_geometry_preserves_size_and_orientation() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")
    dimensions = enclosure.dimensions_for(Face.A)
    slot = Slot(
        face=Face.A,
        center=Point(Decimal("5"), Decimal("-10")),
        length=Decimal("18"),
        width=Decimal("6"),
        angle_degrees=Decimal("45"),
    )

    capsule = capsule_for_slot(slot, dimensions, Decimal("10"))

    assert capsule.length == Decimal("18")
    assert capsule.width == Decimal("6")
    assert capsule.angle_degrees == Decimal("45")
    assert capsule.corner_radius == Decimal("3")
