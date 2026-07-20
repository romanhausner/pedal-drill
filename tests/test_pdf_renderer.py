from decimal import Decimal
from pathlib import Path

import pytest

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.enclosures.validation import DrillLayoutOutsideEnclosureError
from pedal_drill.model import CircularHole, DrillTemplate, Face, Point, Slot
from pedal_drill.renderers import ReportLabPdfRenderer


def test_renderer_creates_one_page_for_each_populated_face(tmp_path: Path) -> None:
    template = DrillTemplate(
        holes=(
            CircularHole(Face.A, Point(Decimal("0"), Decimal("0")), Decimal("9")),
            CircularHole(Face.C, Point(Decimal("0"), Decimal("0")), Decimal("6.5")),
        ),
        slots=(
            Slot(
                Face.A,
                Point(Decimal("10"), Decimal("-10")),
                Decimal("18"),
                Decimal("6"),
                Decimal("45"),
            ),
        ),
        source_format="test",
    )
    output = tmp_path / "template.pdf"

    pages = ReportLabPdfRenderer(margin=Decimal("10")).render(
        template,
        EnclosureCatalog.built_in().get("hammond-1590xx"),
        output,
    )

    assert output.read_bytes().startswith(b"%PDF-")
    assert [page.face for page in pages] == [Face.A, Face.C]
    assert pages[0].width == Decimal("141.20")
    assert pages[0].height == Decimal("165.20")


def test_renderer_validates_before_creating_an_output_file(tmp_path: Path) -> None:
    template = DrillTemplate(
        holes=(
            CircularHole(Face.A, Point(Decimal("60"), Decimal("0")), Decimal("9")),
        ),
        source_format="test",
    )
    output = tmp_path / "outside.pdf"

    with pytest.raises(DrillLayoutOutsideEnclosureError):
        ReportLabPdfRenderer().render(
            template,
            EnclosureCatalog.built_in().get("hammond-1590xx"),
            output,
        )

    assert not output.exists()
