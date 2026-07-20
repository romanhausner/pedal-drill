"""Domain objects for the physical geometry of an enclosure."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from pedal_drill.model import Face


@dataclass(frozen=True, slots=True)
class FaceDimensions:
    """The usable full width and height of one face, in millimetres."""

    width: Decimal
    height: Decimal

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Face dimensions must be greater than zero.")


@dataclass(frozen=True, slots=True)
class EnclosureDefinition:
    """A physical enclosure described entirely by data, not renderer code."""

    identifier: str
    manufacturer: str
    model: str
    faces: Mapping[Face, FaceDimensions]
    unit: str
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("An enclosure identifier is required.")
        missing = set(Face) - set(self.faces)
        if missing:
            names = ", ".join(face.value for face in sorted(missing))
            raise ValueError(f"Dimensions are missing for face(s): {names}.")
        object.__setattr__(self, "faces", MappingProxyType(dict(self.faces)))

    def dimensions_for(self, face: Face) -> FaceDimensions:
        """Return the dimensions of *face*."""

        return self.faces[face]
