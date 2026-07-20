import json
from decimal import Decimal
from pathlib import Path

import pytest

from pedal_drill.enclosures import EnclosureCatalog, EnclosureDefinitionError
from pedal_drill.model import Face


def test_builtin_hammond_1590xx_is_loaded_from_json() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")

    assert enclosure.manufacturer == "Hammond Manufacturing"
    assert enclosure.model == "1590XX"
    assert enclosure.unit == "mm"
    assert enclosure.dimensions_for(Face.A).width == Decimal("121.20")
    assert enclosure.dimensions_for(Face.C).height == Decimal("145.20")


def test_every_bundled_definition_is_complete_and_unique() -> None:
    definitions_directory = (
        Path(__file__).parents[1]
        / "src"
        / "pedal_drill"
        / "enclosures"
        / "definitions"
    )
    definition_files = sorted(definitions_directory.glob("*.json"))
    raw_definitions = [
        json.loads(definition_file.read_text(encoding="utf-8"))
        for definition_file in definition_files
    ]
    catalog = EnclosureCatalog.built_in()

    assert len({definition["id"] for definition in raw_definitions}) == len(
        raw_definitions
    )
    assert len(catalog.all()) == len(raw_definitions)
    for enclosure in catalog.all():
        assert set(enclosure.faces) == set(Face)
        assert enclosure.unit == "mm"
        assert enclosure.source
        assert all(
            dimensions.width > 0 and dimensions.height > 0
            for dimensions in enclosure.faces.values()
        )


def test_catalog_rejects_an_unsupported_definition_unit(tmp_path: Path) -> None:
    (tmp_path / "example.json").write_text(
        """{
          "id": "example",
          "manufacturer": "Example",
          "model": "Example",
          "unit": "in",
          "faces": {
            "A": { "width": 100, "height": 120 },
            "B": { "width": 100, "height": 40 },
            "C": { "width": 40, "height": 120 },
            "D": { "width": 100, "height": 40 },
            "E": { "width": 40, "height": 120 }
          }
        }""",
        encoding="utf-8",
    )

    with pytest.raises(EnclosureDefinitionError, match="Unsupported enclosure unit"):
        EnclosureCatalog.from_directory(tmp_path)
