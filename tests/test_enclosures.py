import json
from decimal import Decimal
from pathlib import Path

import pytest

from pedal_drill.enclosures import (
    EnclosureCatalog,
    EnclosureDefinitionError,
    FaceDimensions,
    FaceShape,
    TrapezoidFaceDimensions,
)
from pedal_drill.model import Face


def test_builtin_hammond_1590xx_is_loaded_from_json() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")

    assert enclosure.manufacturer == "Hammond Manufacturing"
    assert enclosure.model == "1590XX"
    assert enclosure.unit == "mm"
    assert enclosure.dimensions_for(Face.A).width == Decimal("121.20")
    assert isinstance(enclosure.dimensions_for(Face.A), FaceDimensions)
    assert enclosure.dimensions_for(Face.A).shape is FaceShape.RECTANGLE


def test_builtin_hammond_1590xx_uses_verified_trapezoids() -> None:
    enclosure = EnclosureCatalog.built_in().get("hammond-1590xx")

    for face in (Face.B, Face.D):
        dimensions = enclosure.dimensions_for(face)
        assert isinstance(dimensions, TrapezoidFaceDimensions)
        assert dimensions.top_width == Decimal("119.36")
        assert dimensions.bottom_width == Decimal("121.20")
        assert dimensions.height == Decimal("35.20")
    for face in (Face.C, Face.E):
        dimensions = enclosure.dimensions_for(face)
        assert isinstance(dimensions, TrapezoidFaceDimensions)
        assert dimensions.top_width == Decimal("143.36")
        assert dimensions.bottom_width == Decimal("145.20")
        assert dimensions.height == Decimal("35.20")


def test_catalog_parses_rectangle_without_an_explicit_shape(tmp_path: Path) -> None:
    _write_definition(
        tmp_path,
        {face.value: {"width": 40, "height": 60} for face in Face},
    )

    dimensions = EnclosureCatalog.from_directory(tmp_path).get(
        "test-enclosure"
    ).dimensions_for(Face.A)

    assert dimensions == FaceDimensions(Decimal("40"), Decimal("60"))


def test_catalog_parses_a_symmetric_trapezoid(tmp_path: Path) -> None:
    faces = {face.value: {"width": 40, "height": 60} for face in Face}
    faces["B"] = {
        "shape": "trapezoid",
        "top_width": 38.2,
        "bottom_width": 40,
        "height": 20,
    }
    _write_definition(tmp_path, faces)

    dimensions = EnclosureCatalog.from_directory(tmp_path).get(
        "test-enclosure"
    ).dimensions_for(Face.B)

    assert dimensions == TrapezoidFaceDimensions(
        Decimal("38.2"), Decimal("40"), Decimal("20")
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("top_width", 0),
        ("bottom_width", 0),
        ("height", 0),
        ("top_width", -1),
        ("bottom_width", -1),
        ("height", -1),
    ],
)
def test_catalog_rejects_non_positive_trapezoid_dimensions(
    tmp_path: Path, field: str, value: int
) -> None:
    faces = {face.value: {"width": 40, "height": 60} for face in Face}
    trapezoid = {
        "shape": "trapezoid",
        "top_width": 38,
        "bottom_width": 40,
        "height": 20,
    }
    trapezoid[field] = value
    faces["B"] = trapezoid
    _write_definition(tmp_path, faces)

    with pytest.raises(EnclosureDefinitionError, match="greater than zero"):
        EnclosureCatalog.from_directory(tmp_path)


@pytest.mark.parametrize(
    ("identifier", "model"),
    [
        ("hammond-1590g", "1590G"),
        ("hammond-1590x", "1590X"),
        ("hammond-1550b", "1550B"),
    ],
)
def test_new_hammond_definitions_are_complete(
    identifier: str, model: str
) -> None:
    enclosure = EnclosureCatalog.built_in().get(identifier)

    assert enclosure.manufacturer == "Hammond"
    assert enclosure.model == model
    assert enclosure.unit == "mm"
    assert set(enclosure.faces) == set(Face)
    assert all(
        dimensions.width > 0 and dimensions.height > 0
        for dimensions in enclosure.faces.values()
    )


def test_every_bundled_definition_is_complete() -> None:
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

    assert len(catalog.all()) == len(raw_definitions)
    for enclosure in catalog.all():
        assert set(enclosure.faces) == set(Face)
        assert enclosure.unit == "mm"
        assert enclosure.source
        assert all(
            dimensions.width > 0 and dimensions.height > 0
            for dimensions in enclosure.faces.values()
        )


def test_bundled_definition_ids_are_unique() -> None:
    definitions_directory = (
        Path(__file__).parents[1]
        / "src"
        / "pedal_drill"
        / "enclosures"
        / "definitions"
    )
    identifiers = [
        json.loads(path.read_text(encoding="utf-8"))["id"]
        for path in definitions_directory.glob("*.json")
    ]

    assert len(identifiers) == len(set(identifiers))


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


def _write_definition(tmp_path: Path, faces: dict[str, object]) -> None:
    (tmp_path / "test.json").write_text(
        json.dumps(
            {
                "id": "test-enclosure",
                "manufacturer": "Test",
                "model": "Test",
                "unit": "mm",
                "faces": faces,
            }
        ),
        encoding="utf-8",
    )
