"""Safe parser for pedal-drill's native versioned YAML format."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError, SafeConstructor
from yaml.nodes import MappingNode, ScalarNode

from pedal_drill.model import (
    CircularHole,
    DrillTemplate,
    Face,
    LineSegment,
    Point,
    Slot,
)
from pedal_drill.parsers.base import ParseError

_FORMAT_VERSION = "pedal-drill-1"
_ROOT_FIELDS = frozenset(("format", "enclosure", "unit", "features"))
_REQUIRED_ROOT_FIELDS = frozenset(("format", "enclosure", "features"))
_FEATURE_FIELDS = {
    "hole": frozenset(("type", "face", "center", "diameter")),
    "slot": frozenset(
        ("type", "face", "center", "length", "width", "angle", "drill_ends")
    ),
    "line": frozenset(("type", "face", "from", "to")),
}
_REQUIRED_FEATURE_FIELDS = {
    "hole": frozenset(("type", "face", "center", "diameter")),
    "slot": frozenset(("type", "face", "center", "length", "width")),
    "line": frozenset(("type", "face", "from", "to")),
}


class _NativeSafeLoader(yaml.SafeLoader):
    """Safe loader with unique keys and lexical Decimal construction."""


def _construct_unique_mapping(
    loader: _NativeSafeLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    if not isinstance(node, MappingNode):
        raise ConstructorError(None, None, "expected a mapping", node.start_mark)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


def _construct_decimal_integer(
    loader: _NativeSafeLoader, node: ScalarNode
) -> Decimal:
    return Decimal(SafeConstructor.construct_yaml_int(loader, node))


def _construct_decimal_float(
    loader: _NativeSafeLoader, node: ScalarNode
) -> Decimal:
    lexical = loader.construct_scalar(node).replace("_", "")
    special = {
        ".inf": "Infinity",
        "+.inf": "Infinity",
        "-.inf": "-Infinity",
        ".nan": "NaN",
    }
    normalized = special.get(lexical.lower(), lexical)
    try:
        return Decimal(normalized)
    except InvalidOperation as error:
        raise ConstructorError(
            "while constructing a decimal",
            node.start_mark,
            f"invalid numeric scalar {lexical!r}",
            node.start_mark,
        ) from error


_NativeSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)
_NativeSafeLoader.add_constructor(
    "tag:yaml.org,2002:int", _construct_decimal_integer
)
_NativeSafeLoader.add_constructor(
    "tag:yaml.org,2002:float", _construct_decimal_float
)


@dataclass(frozen=True, slots=True)
class NativeYamlDocument:
    """A parsed template plus its catalog enclosure selection."""

    template: DrillTemplate
    enclosure_id: str


class NativeYamlParser:
    """Convert ``pedal-drill-1`` YAML into the shared domain model."""

    source_format = _FORMAT_VERSION

    def parse_file(self, path: Path) -> DrillTemplate:
        """Parse a UTF-8 YAML file and return only its drill template."""

        return self.parse_document_file(path).template

    def parse_document_file(self, path: Path) -> NativeYamlDocument:
        """Parse a UTF-8 YAML file including its enclosure identifier."""

        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise ParseError(f"Could not read native YAML {path}: {error}") from error
        return self.parse_document(text, source=str(path), name=path.stem)

    def parse_text(self, text: str, *, name: str | None = None) -> DrillTemplate:
        """Parse YAML text and return only its drill template."""

        return self.parse_document(
            text,
            source=name or "<input>",
            name=name,
        ).template

    def parse_document(
        self,
        text: str,
        *,
        source: str = "<input>",
        name: str | None = None,
    ) -> NativeYamlDocument:
        """Load, validate, and convert one native YAML document."""

        try:
            root = yaml.load(text, Loader=_NativeSafeLoader)
        except yaml.YAMLError as error:
            detail = getattr(error, "problem", None) or str(error).splitlines()[0]
            raise ParseError(f"{source}: invalid YAML: {detail}") from error
        if not isinstance(root, Mapping):
            raise ParseError(f"{source}: document root must be a mapping.")
        self._validate_fields(
            root,
            allowed=_ROOT_FIELDS,
            required=_REQUIRED_ROOT_FIELDS,
            context=source,
            kind="root",
        )
        if root["format"] != _FORMAT_VERSION:
            raise ParseError(
                f"{source}: field 'format' must equal {_FORMAT_VERSION!r}; "
                f"got {root['format']!r}."
            )
        if "unit" in root and root["unit"] != "mm":
            raise ParseError(
                f"{source}: field 'unit' must equal 'mm'; got {root['unit']!r}."
            )
        enclosure_id = root["enclosure"]
        if not isinstance(enclosure_id, str) or not enclosure_id:
            raise ParseError(f"{source}: field 'enclosure' must be a non-empty string.")
        features = root["features"]
        if not isinstance(features, list):
            raise ParseError(f"{source}: field 'features' must be a list.")

        holes: list[CircularHole] = []
        slots: list[Slot] = []
        lines: list[LineSegment] = []
        for index, feature in enumerate(features, start=1):
            context = f"{source}: feature {index}"
            if not isinstance(feature, Mapping):
                raise ParseError(f"{context}: feature must be a mapping.")
            feature_type = feature.get("type")
            if (
                not isinstance(feature_type, str)
                or feature_type not in _FEATURE_FIELDS
            ):
                raise ParseError(
                    f"{context}: unknown feature type {feature_type!r}."
                )
            self._validate_fields(
                feature,
                allowed=_FEATURE_FIELDS[feature_type],
                required=_REQUIRED_FEATURE_FIELDS[feature_type],
                context=context,
                kind=f"feature type {feature_type!r}",
            )
            if feature_type == "hole":
                holes.append(self._hole(feature, context))
            elif feature_type == "slot":
                slots.append(self._slot(feature, context))
            else:
                lines.append(self._line(feature, context))

        return NativeYamlDocument(
            template=DrillTemplate(
                holes=tuple(holes),
                slots=tuple(slots),
                lines=tuple(lines),
                source_format=self.source_format,
                name=name,
            ),
            enclosure_id=enclosure_id,
        )

    @staticmethod
    def _validate_fields(
        values: Mapping[Any, Any],
        *,
        allowed: frozenset[str],
        required: frozenset[str],
        context: str,
        kind: str,
    ) -> None:
        unknown = tuple(key for key in values if key not in allowed)
        if unknown:
            field = unknown[0]
            raise ParseError(f"{context}: unknown field {field!r} for {kind}.")
        missing = tuple(sorted(field for field in required if field not in values))
        if missing:
            raise ParseError(f"{context}: missing required field {missing[0]!r}.")

    @classmethod
    def _hole(cls, feature: Mapping[Any, Any], context: str) -> CircularHole:
        diameter = cls._number(feature["diameter"], "diameter", context)
        if diameter <= 0:
            raise ParseError(f"{context}: hole diameter must be greater than zero.")
        return CircularHole(
            face=cls._face(feature["face"], context),
            center=cls._point(feature["center"], "center", context),
            diameter=diameter,
        )

    @classmethod
    def _slot(cls, feature: Mapping[Any, Any], context: str) -> Slot:
        length = cls._number(feature["length"], "length", context)
        width = cls._number(feature["width"], "width", context)
        angle = cls._number(feature.get("angle", Decimal("0")), "angle", context)
        drill_ends = feature.get("drill_ends", False)
        if width <= 0:
            raise ParseError(f"{context}: slot width must be greater than zero.")
        if length < width:
            raise ParseError(
                f"{context}: slot length must be greater than or equal to width."
            )
        if not isinstance(drill_ends, bool):
            raise ParseError(f"{context}: field 'drill_ends' must be a boolean.")
        return Slot(
            face=cls._face(feature["face"], context),
            center=cls._point(feature["center"], "center", context),
            length=length,
            width=width,
            angle_degrees=angle,
            drill_ends=drill_ends,
        )

    @classmethod
    def _line(cls, feature: Mapping[Any, Any], context: str) -> LineSegment:
        start = cls._point(feature["from"], "from", context)
        end = cls._point(feature["to"], "to", context)
        if start == end:
            raise ParseError(f"{context}: line start and end must be different.")
        return LineSegment(
            face=cls._face(feature["face"], context),
            start=start,
            end=end,
        )

    @staticmethod
    def _face(value: Any, context: str) -> Face:
        try:
            return Face(value)
        except (TypeError, ValueError) as error:
            raise ParseError(
                f"{context}: field 'face' must be one of A, B, C, D, E; "
                f"got {value!r}."
            ) from error

    @classmethod
    def _point(cls, value: Any, field: str, context: str) -> Point:
        if not isinstance(value, list) or len(value) != 2:
            raise ParseError(
                f"{context}: field {field!r} must contain exactly two numbers."
            )
        return Point(
            cls._number(value[0], f"{field}[0]", context),
            cls._number(value[1], f"{field}[1]", context),
        )

    @staticmethod
    def _number(value: Any, field: str, context: str) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, Decimal):
            raise ParseError(f"{context}: field {field!r} must be a number.")
        if not value.is_finite():
            raise ParseError(f"{context}: field {field!r} must be finite.")
        return value
