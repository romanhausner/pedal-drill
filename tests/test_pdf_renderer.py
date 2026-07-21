from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from reportlab.pdfgen.canvas import Canvas

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.enclosures.validation import DrillLayoutOutsideEnclosureError
from pedal_drill.model import CircularHole, DrillTemplate, Face, Point, Slot
from pedal_drill.renderers import ReportLabPdfRenderer
from pedal_drill.renderers.pdf import RenderedPage, _PRINT_INSTRUCTIONS


def test_renderer_creates_overview_then_one_page_for_each_populated_face(
    tmp_path: Path,
) -> None:
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

    renderer = ReportLabPdfRenderer(margin=Decimal("10"))
    with patch.object(
        renderer,
        "_draw_instructions",
        wraps=renderer._draw_instructions,
    ) as draw_instructions:
        pages = renderer.render(
            template,
            EnclosureCatalog.built_in().get("hammond-1590xx"),
            output,
        )

    assert output.read_bytes().startswith(b"%PDF-")
    assert [page.face for page in pages] == [None, Face.A, Face.C]
    assert pages[0].is_overview
    assert pages[0].width == Decimal("200")
    assert pages[0].height == Decimal("269")
    assert pages[1].width == Decimal("141.20")
    assert pages[1].height == Decimal("175.20")
    assert pages[2].width == Decimal("55.20")
    assert pages[2].height == Decimal("175.20")
    assert draw_instructions.call_count == 2


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


class _InstructionCanvas:
    def __init__(self) -> None:
        self.instructions: list[str] = []

    def setFont(self, _: str, __: float) -> None:  # noqa: N802
        pass

    def drawCentredString(self, _: float, __: float, text: str) -> None:  # noqa: N802
        self.instructions.append(text)


def test_instruction_text_is_drawn() -> None:
    canvas = _InstructionCanvas()
    page = RenderedPage(Face.A, Decimal("100"), Decimal("120"))

    ReportLabPdfRenderer()._draw_instructions(cast(Canvas, canvas), page)

    assert canvas.instructions == list(_PRINT_INSTRUCTIONS)
