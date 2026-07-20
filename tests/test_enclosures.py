from decimal import Decimal

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.model import Face


def test_builtin_hammond_1590xx_is_loaded_from_json() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")

    assert enclosure.manufacturer == "Hammond Manufacturing"
    assert enclosure.model == "1590XX"
    assert enclosure.dimensions_for(Face.A).width == Decimal("121.20")
    assert enclosure.dimensions_for(Face.C).height == Decimal("145.20")
