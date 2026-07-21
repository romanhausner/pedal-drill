"""Tests for the versioned native pedal-drill YAML input format."""

from decimal import Decimal
from pathlib import Path

import pytest

from pedal_drill.model import Face, Point
from pedal_drill.parsers import NativeYamlParser, ParseError, parse_input_file


def _document(features: str, **root: str) -> str:
    values = {
        "format": "pedal-drill-1",
        "enclosure": "hammond-1590bb",
        "unit": "mm",
        **root,
    }
    header = "\n".join(f"{key}: {value}" for key, value in values.items())
    if features.strip() == "[]":
        return f"{header}\nfeatures: []\n"
    return f"{header}\nfeatures:\n{features}"


def test_minimal_native_yaml_hole() -> None:
    document = NativeYamlParser().parse_document(
        _document(
            """  - type: hole
    face: A
    center: [0, 30]
    diameter: 7
"""
        ),
        source="layout.yaml",
    )

    assert document.enclosure_id == "hammond-1590bb"
    assert document.template.source_format == "pedal-drill-1"
    assert document.template.holes[0].face is Face.A
    assert document.template.holes[0].center == Point(Decimal("0"), Decimal("30"))
    assert document.template.holes[0].diameter == Decimal("7")


def test_native_yaml_maps_holes_slots_and_lines_to_domain_types() -> None:
    document = NativeYamlParser().parse_document_file(
        Path("tests/fixtures/native/example-layout.yaml")
    )
    template = document.template

    assert len(template.holes) == 2
    assert len(template.slots) == 1
    assert len(template.lines) == 1
    assert template.slots[0].length == Decimal("18")
    assert template.slots[0].width == Decimal("6")
    assert template.slots[0].angle_degrees == Decimal("30")
    assert template.slots[0].drill_ends is True
    assert template.lines[0].start == Point(Decimal("-10"), Decimal("-15"))


def test_coordinates_are_supported_on_every_face() -> None:
    features = "".join(
        f"  - type: hole\n    face: {face.value}\n"
        f"    center: [{index - 2}, {2 - index}]\n    diameter: 1\n"
        for index, face in enumerate(Face)
    )
    template = NativeYamlParser().parse_text(_document(features))

    assert tuple(hole.face for hole in template.holes) == tuple(Face)
    assert template.holes[0].center == Point(Decimal("-2"), Decimal("2"))
    assert template.holes[2].center == Point(Decimal("0"), Decimal("0"))
    assert template.holes[4].center == Point(Decimal("2"), Decimal("-2"))


@pytest.mark.parametrize("angle", ["0", "45", "90", "-30"])
def test_slot_angles_are_preserved(angle: str) -> None:
    template = NativeYamlParser().parse_text(
        _document(
            f"""  - type: slot
    face: A
    center: [0, 0]
    length: 18
    width: 6
    angle: {angle}
"""
        )
    )

    assert template.slots[0].angle_degrees == Decimal(angle)


@pytest.mark.parametrize(
    ("drill_field", "expected"),
    [("", False), ("    drill_ends: false\n", False), ("    drill_ends: true\n", True)],
)
def test_slot_drill_ends_default_and_explicit_values(
    drill_field: str, expected: bool
) -> None:
    template = NativeYamlParser().parse_text(
        _document(
            """  - type: slot
    face: A
    center: [0, 0]
    length: 18
    width: 6
"""
            + drill_field
        )
    )

    assert template.slots[0].drill_ends is expected


def test_decimal_lexemes_are_preserved_without_float_rounding() -> None:
    template = NativeYamlParser().parse_text(
        _document(
            """  - type: hole
    face: A
    center: [0.1, -0.1]
    diameter: 6.4
"""
        )
    )

    assert template.holes[0].center == Point(Decimal("0.1"), Decimal("-0.1"))
    assert template.holes[0].diameter == Decimal("6.4")


@pytest.mark.parametrize(
    ("root_override", "message"),
    [
        ({"format": "pedal-drill-2"}, "field 'format' must equal"),
        ({"unit": "in"}, "field 'unit' must equal 'mm'"),
    ],
)
def test_invalid_root_values_are_rejected(
    root_override: dict[str, str], message: str
) -> None:
    with pytest.raises(ParseError, match=message):
        NativeYamlParser().parse_text(_document("[]\n", **root_override))


def test_unknown_root_field_is_rejected() -> None:
    with pytest.raises(ParseError, match="unknown field 'origin' for root"):
        NativeYamlParser().parse_text(
            _document("[]\n").replace("features:", "origin: center\nfeatures:")
        )


def test_unknown_feature_type_is_rejected() -> None:
    with pytest.raises(ParseError, match="unknown feature type 'rectangle'"):
        NativeYamlParser().parse_text(
            _document("  - type: rectangle\n    face: A\n")
        )


@pytest.mark.parametrize(
    ("feature", "field", "feature_type"),
    [
        (
            "  - type: hole\n    face: A\n    center: [0, 0]\n"
            "    diameter: 3\n    radius: 1.5\n",
            "radius",
            "hole",
        ),
        (
            "  - type: slot\n    face: A\n    center: [0, 0]\n"
            "    length: 8\n    width: 3\n    diameter: 3\n",
            "diameter",
            "slot",
        ),
        (
            "  - type: line\n    face: A\n    from: [0, 0]\n"
            "    to: [1, 1]\n    width: 1\n",
            "width",
            "line",
        ),
    ],
)
def test_unknown_feature_fields_are_rejected(
    feature: str, field: str, feature_type: str
) -> None:
    with pytest.raises(
        ParseError,
        match=rf"unknown field '{field}' for feature type '{feature_type}'",
    ):
        NativeYamlParser().parse_text(_document(feature))


def test_invalid_face_and_missing_field_include_feature_location() -> None:
    invalid_face = _document(
        "  - type: hole\n    face: rear\n    center: [0, 0]\n    diameter: 3\n"
    )
    missing = _document("  - type: hole\n    face: A\n    center: [0, 0]\n")

    with pytest.raises(ParseError, match="feature 1: field 'face' must be one of"):
        NativeYamlParser().parse_text(invalid_face, name="layout.yaml")
    with pytest.raises(
        ParseError, match="feature 1: missing required field 'diameter'"
    ):
        NativeYamlParser().parse_text(missing, name="layout.yaml")


@pytest.mark.parametrize(
    "field",
    ["center: [0]", "center: [0, 1, 2]", "center: value", "center: [0, bad]"],
)
def test_malformed_centers_are_rejected(field: str) -> None:
    feature = f"  - type: hole\n    face: A\n    {field}\n    diameter: 3\n"

    with pytest.raises(ParseError, match="field 'center"):
        NativeYamlParser().parse_text(_document(feature))


@pytest.mark.parametrize("diameter", ["0", "-1"])
def test_non_positive_hole_diameters_are_rejected(diameter: str) -> None:
    feature = (
        "  - type: hole\n    face: A\n    center: [0, 0]\n"
        f"    diameter: {diameter}\n"
    )

    with pytest.raises(ParseError, match="hole diameter must be greater than zero"):
        NativeYamlParser().parse_text(_document(feature))


@pytest.mark.parametrize("width", ["0", "-1"])
def test_non_positive_slot_widths_are_rejected(width: str) -> None:
    feature = (
        "  - type: slot\n    face: A\n    center: [0, 0]\n"
        f"    length: 6\n    width: {width}\n"
    )

    with pytest.raises(ParseError, match="slot width must be greater than zero"):
        NativeYamlParser().parse_text(_document(feature))


def test_slot_length_must_not_be_smaller_than_width() -> None:
    feature = (
        "  - type: slot\n    face: A\n    center: [0, 0]\n"
        "    length: 5\n    width: 6\n"
    )

    with pytest.raises(ParseError, match="length must be greater than or equal"):
        NativeYamlParser().parse_text(_document(feature))


def test_slot_drill_ends_must_be_boolean() -> None:
    feature = (
        "  - type: slot\n    face: A\n    center: [0, 0]\n"
        "    length: 6\n    width: 3\n    drill_ends: 1\n"
    )

    with pytest.raises(ParseError, match="field 'drill_ends' must be a boolean"):
        NativeYamlParser().parse_text(_document(feature))


def test_equal_slot_length_and_width_is_accepted() -> None:
    feature = (
        "  - type: slot\n    face: A\n    center: [0, 0]\n"
        "    length: 6\n    width: 6\n"
    )

    assert (
        NativeYamlParser().parse_text(_document(feature)).slots[0].length
        == Decimal("6")
    )


@pytest.mark.parametrize("field", ["from: [0]", "to: [1, 2, 3]"])
def test_malformed_line_endpoints_are_rejected(field: str) -> None:
    values = {"from": "[0, 0]", "to": "[1, 1]"}
    name, value = field.split(": ", maxsplit=1)
    values[name] = value
    feature = (
        "  - type: line\n    face: A\n"
        f"    from: {values['from']}\n    to: {values['to']}\n"
    )

    with pytest.raises(ParseError, match=f"field '{name}'"):
        NativeYamlParser().parse_text(_document(feature))


def test_identical_line_endpoints_are_rejected() -> None:
    feature = (
        "  - type: line\n    face: A\n"
        "    from: [1, 2]\n    to: [1, 2]\n"
    )

    with pytest.raises(ParseError, match="line start and end must be different"):
        NativeYamlParser().parse_text(_document(feature))


@pytest.mark.parametrize(
    "numeric_field",
    ["diameter: true", "center: [false, 0]"],
)
def test_booleans_are_not_accepted_as_numbers(numeric_field: str) -> None:
    if numeric_field.startswith("diameter"):
        feature = (
            "  - type: hole\n    face: A\n    center: [0, 0]\n"
            f"    {numeric_field}\n"
        )
    else:
        feature = (
            f"  - type: hole\n    face: A\n    {numeric_field}\n"
            "    diameter: 3\n"
        )

    with pytest.raises(ParseError, match="must be a number"):
        NativeYamlParser().parse_text(_document(feature))


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf"])
def test_non_finite_numbers_are_rejected(value: str) -> None:
    feature = (
        "  - type: hole\n    face: A\n    center: [0, 0]\n"
        f"    diameter: {value}\n"
    )

    with pytest.raises(ParseError, match="must be finite"):
        NativeYamlParser().parse_text(_document(feature))


def test_invalid_yaml_and_duplicate_keys_are_reported_without_tracebacks() -> None:
    with pytest.raises(ParseError, match="invalid YAML"):
        NativeYamlParser().parse_text("format: [unterminated")
    duplicate = _document(
        "  - type: hole\n    face: A\n    face: B\n"
        "    center: [0, 0]\n    diameter: 3\n"
    )
    with pytest.raises(ParseError, match="duplicate key 'face'"):
        NativeYamlParser().parse_text(duplicate)


def test_executable_yaml_tags_are_rejected_by_the_safe_loader() -> None:
    with pytest.raises(ParseError, match="invalid YAML"):
        NativeYamlParser().parse_text(
            "!!python/object/apply:os.system ['echo unsafe']"
        )


def test_input_dispatch_uses_extensions_without_content_guessing(
    tmp_path: Path,
) -> None:
    yaml_path = tmp_path / "layout.YML"
    yaml_path.write_text(
        _document(
            "  - type: hole\n    face: A\n    center: [0, 0]\n    diameter: 3\n"
        ),
        encoding="utf-8",
    )

    parsed = parse_input_file(yaml_path)

    assert parsed.enclosure_id == "hammond-1590bb"
    assert len(parsed.template.holes) == 1
    with pytest.raises(ParseError, match="Unsupported input extension"):
        parse_input_file(tmp_path / "layout.json")
