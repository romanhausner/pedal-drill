"""Format- and renderer-independent objects that describe a drill template."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Face(StrEnum):
    """The five drillable faces in Tayda's enclosure coordinate convention."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


@dataclass(frozen=True, slots=True)
class Point:
    """A two-dimensional point in millimetres, relative to its face origin."""

    x: Decimal
    y: Decimal


@dataclass(frozen=True, slots=True)
class CircularHole:
    """One circular hole to drill on an enclosure face."""

    face: Face
    center: Point
    diameter: Decimal

    def __post_init__(self) -> None:
        if self.diameter <= 0:
            raise ValueError("A hole diameter must be greater than zero.")


@dataclass(frozen=True, slots=True)
class LineSegment:
    """A straight construction line imported from a source template."""

    face: Face
    start: Point
    end: Point


@dataclass(frozen=True, slots=True)
class Slot:
    """A capsule-shaped slot with an explicit size and orientation."""

    face: Face
    center: Point
    length: Decimal
    width: Decimal
    angle_degrees: Decimal

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError("A slot width must be greater than zero.")
        if self.length < self.width:
            raise ValueError("A slot length must be at least its width.")


@dataclass(frozen=True, slots=True)
class DrillTemplate:
    """A complete source-independent drill layout.

    Enclosure dimensions are intentionally absent: an import format may not
    identify an enclosure, and a future renderer can resolve them independently.
    """

    holes: tuple[CircularHole, ...]
    source_format: str
    lines: tuple[LineSegment, ...] = ()
    slots: tuple[Slot, ...] = ()
    name: str | None = None

    def holes_on(self, face: Face) -> tuple[CircularHole, ...]:
        """Return holes on *face*, preserving their source order."""

        return tuple(hole for hole in self.holes if hole.face is face)
