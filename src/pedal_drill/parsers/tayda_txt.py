"""Parser for the tab-delimited TXT export produced by Tayda's drill tool."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from pedal_drill.model import CircularHole, DrillTemplate, Face, LineSegment, Point
from pedal_drill.parsers.base import ParseError


class TaydaTxtParser:
    """Convert Tayda's unheadered, tab-delimited export into a drill template.

    A four-column row is a circular hole: ``side, diameter, x, y``. A six-column
    row whose second value is ``0`` is a line: ``side, 0, x1, y1, x2, y2``.
    Coordinates remain in Tayda's centre-of-face coordinate system.
    """

    source_format = "tayda-txt"

    def parse_file(self, path: Path) -> DrillTemplate:
        """Read a UTF-8 text export and parse it."""

        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise ParseError(f"Could not read Tayda export {path}: {error}") from error
        return self.parse_text(text, name=path.stem)

    def parse_text(self, text: str, *, name: str | None = None) -> DrillTemplate:
        """Parse a Tayda TXT export without requiring an enclosure definition."""

        holes: list[CircularHole] = []
        lines: list[LineSegment] = []
        records = [
            (number, line)
            for number, line in enumerate(text.splitlines(), start=1)
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if not records:
            raise ParseError("The Tayda export is empty.")

        for line_number, line in records:
            fields = [field.strip() for field in line.split("\t")]
            if len(fields) == 4:
                holes.append(self._parse_hole(fields, line_number))
            elif len(fields) == 6:
                lines.append(self._parse_line(fields, line_number))
            else:
                raise ParseError(
                    f"Line {line_number}: expected 4 columns for a hole or 6 for a line."
                )
        return DrillTemplate(
            holes=tuple(holes),
            lines=tuple(lines),
            source_format=self.source_format,
            name=name,
        )

    @staticmethod
    def _parse_hole(fields: list[str], line_number: int) -> CircularHole:
        try:
            return CircularHole(
                face=TaydaTxtParser._face(fields[0], line_number),
                diameter=TaydaTxtParser._decimal(fields[1], "diameter", line_number),
                center=Point(
                    x=TaydaTxtParser._decimal(fields[2], "x", line_number),
                    y=TaydaTxtParser._decimal(fields[3], "y", line_number),
                ),
            )
        except ValueError as error:
            raise ParseError(f"Line {line_number}: {error}") from error

    @staticmethod
    def _parse_line(fields: list[str], line_number: int) -> LineSegment:
        marker = TaydaTxtParser._decimal(fields[1], "line marker", line_number)
        if marker != 0:
            raise ParseError(f"Line {line_number}: line marker must be 0.")
        return LineSegment(
            face=TaydaTxtParser._face(fields[0], line_number),
            start=Point(
                x=TaydaTxtParser._decimal(fields[2], "x1", line_number),
                y=TaydaTxtParser._decimal(fields[3], "y1", line_number),
            ),
            end=Point(
                x=TaydaTxtParser._decimal(fields[4], "x2", line_number),
                y=TaydaTxtParser._decimal(fields[5], "y2", line_number),
            ),
        )

    @staticmethod
    def _face(value: str, line_number: int) -> Face:
        try:
            return Face(value.upper())
        except ValueError as error:
            raise ParseError(
                f"Line {line_number}: side must be one of A, B, C, D, E."
            ) from error

    @staticmethod
    def _decimal(value: str, label: str, line_number: int) -> Decimal:
        """Parse a finite decimal and attach input location to failures."""

        try:
            decimal = Decimal(value)
        except InvalidOperation as error:
            raise ParseError(f"Line {line_number}: {label} must be a number.") from error
        if not decimal.is_finite():
            raise ParseError(f"Line {line_number}: {label} must be finite.")
        return decimal
