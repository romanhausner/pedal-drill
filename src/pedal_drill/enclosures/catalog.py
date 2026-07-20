"""Load JSON enclosure definitions from built-in or user-supplied directories."""

from __future__ import annotations

import json
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path

from pedal_drill.enclosures.model import EnclosureDefinition, FaceDimensions
from pedal_drill.model import Face


class EnclosureDefinitionError(ValueError):
    """Raised when an enclosure definition JSON file is invalid."""


class EnclosureCatalog:
    """An index of enclosure definitions loaded from one or more directories."""

    def __init__(self, definitions: Iterable[EnclosureDefinition]) -> None:
        self._definitions = {definition.identifier: definition for definition in definitions}

    @classmethod
    def built_in(cls) -> EnclosureCatalog:
        """Load definitions shipped with pedal-drill."""

        directory = files("pedal_drill.enclosures").joinpath("definitions")
        return cls(_load_definition_file(Path(entry)) for entry in directory.iterdir() if entry.suffix == ".json")

    @classmethod
    def from_directory(cls, directory: Path) -> EnclosureCatalog:
        """Load all JSON definitions in a user-supplied *directory*."""

        return cls(_load_definition_file(path) for path in sorted(directory.glob("*.json")))

    def get(self, identifier: str) -> EnclosureDefinition:
        """Return an enclosure by its stable identifier."""

        try:
            return self._definitions[identifier]
        except KeyError as error:
            raise KeyError(f"Unknown enclosure definition: {identifier}") from error

    def all(self) -> tuple[EnclosureDefinition, ...]:
        """Return definitions in stable identifier order."""

        return tuple(self._definitions[key] for key in sorted(self._definitions))


def _load_definition_file(path: Path) -> EnclosureDefinition:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EnclosureDefinitionError(f"Could not load {path}: {error}") from error
    try:
        faces = {
            Face(name): FaceDimensions(
                width=_decimal(dimensions["width_mm"]),
                height=_decimal(dimensions["height_mm"]),
            )
            for name, dimensions in raw["faces"].items()
        }
        return EnclosureDefinition(
            identifier=raw["id"],
            manufacturer=raw["manufacturer"],
            model=raw["model"],
            faces=faces,
            source=raw.get("source"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EnclosureDefinitionError(f"Invalid enclosure definition {path}: {error}") from error


def _decimal(value: object) -> Decimal:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise EnclosureDefinitionError(f"Dimension {value!r} is not a number.") from error
    if not decimal.is_finite():
        raise EnclosureDefinitionError(f"Dimension {value!r} must be finite.")
    return decimal
