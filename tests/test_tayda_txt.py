from decimal import Decimal
from pathlib import Path

import pytest

from pedal_drill.model import Face
from pedal_drill.parsers import ParseError, TaydaTxtParser


def test_parses_tayda_hole_and_line_records() -> None:
    template = TaydaTxtParser().parse_text(
        "# Tungsten\nA\t3.0\t-17.027\t10.84\nD\t0\t16.21\t3.8\t16.21\t-4.2\n",
        name="tungsten",
    )

    assert template.name == "tungsten"
    assert template.source_format == "tayda-txt"
    assert template.holes[0].face is Face.A
    assert template.holes[0].center.x == Decimal("-17.027")
    assert template.lines[0].face is Face.D
    assert template.lines[0].end.y == Decimal("-4.2")


def test_parse_file_removes_utf8_byte_order_mark(tmp_path: Path) -> None:
    export = tmp_path / "layout.txt"
    export.write_text("A\t3\t0\t0\n", encoding="utf-8-sig")

    template = TaydaTxtParser().parse_file(export)

    assert template.name == "layout"
    assert len(template.holes) == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("A\t3\t0\n", "expected 4 columns"),
        ("Z\t3\t0\t0\n", "side must"),
        ("A\tno\t0\t3\n", "diameter must"),
        ("A\tNaN\t0\t3\n", "diameter must be finite"),
        ("A\t0\t0\t3\n", "greater than zero"),
        ("A\t1\t0\t0\t1\t1\n", "line marker must be 0"),
    ],
)
def test_rejects_invalid_records(text: str, message: str) -> None:
    with pytest.raises(ParseError, match=message):
        TaydaTxtParser().parse_text(text)
