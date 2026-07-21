"""Data-driven enclosure definitions and their loader."""

from pedal_drill.enclosures.catalog import EnclosureCatalog, EnclosureDefinitionError
from pedal_drill.enclosures.model import (
    EnclosureDefinition,
    FaceDimensions,
    FaceGeometry,
    FaceShape,
    TrapezoidFaceDimensions,
)

__all__ = [
    "EnclosureCatalog",
    "EnclosureDefinition",
    "EnclosureDefinitionError",
    "FaceDimensions",
    "FaceGeometry",
    "FaceShape",
    "TrapezoidFaceDimensions",
]
