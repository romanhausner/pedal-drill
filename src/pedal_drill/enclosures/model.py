"""Domain objects for the physical geometry of an enclosure."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeAlias

from pedal_drill.model import Face


class FaceShape(StrEnum):
    """Shapes supported by the enclosure-definition JSON schema."""

    RECTANGLE = "rectangle"
    TRAPEZOID = "trapezoid"


@dataclass(frozen=True, slots=True)
class FaceDimensions:
    """A rectangular usable face envelope, in millimetres."""

    width: Decimal
    height: Decimal

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Face dimensions must be greater than zero.")

    @property
    def shape(self) -> FaceShape:
        """Return the explicit domain shape for this legacy rectangle type."""

        return FaceShape.RECTANGLE


@dataclass(frozen=True, slots=True)
class TrapezoidFaceDimensions:
    """A centred symmetric trapezoid in the face coordinate system.

    ``top_width`` is adjacent to the closed Face A surface and
    ``bottom_width`` is adjacent to the open/lid side.
    """

    top_width: Decimal
    bottom_width: Decimal
    height: Decimal

    def __post_init__(self) -> None:
        if self.top_width <= 0 or self.bottom_width <= 0 or self.height <= 0:
            raise ValueError("Trapezoid dimensions must be greater than zero.")

    @property
    def width(self) -> Decimal:
        """Return the maximum width used for bounds and page sizing."""

        return max(self.top_width, self.bottom_width)

    @property
    def shape(self) -> FaceShape:
        """Return the external-schema shape identifier."""

        return FaceShape.TRAPEZOID


FaceGeometry: TypeAlias = FaceDimensions | TrapezoidFaceDimensions


@dataclass(frozen=True, slots=True)
class EnclosureDefinition:
    """A physical enclosure described entirely by data, not renderer code."""

    identifier: str
    manufacturer: str
    model: str
    faces: Mapping[Face, FaceGeometry]
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

    def dimensions_for(self, face: Face) -> FaceGeometry:
        """Return the dimensions of *face*."""

        return self.faces[face]
