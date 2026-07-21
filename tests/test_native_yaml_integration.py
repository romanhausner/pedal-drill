"""Integration tests joining native YAML to validation, rendering, and CLI."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from reportlab.pdfgen.canvas import Canvas

from pedal_drill.cli import main
from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.enclosures.validation import (
    DrillLayoutOutsideEnclosureError,
    validate_template_fits_enclosure,
)
from pedal_drill.geometry import (
    capsule_centerline_endpoints,
    capsule_for_slot,
    capsule_path,
)
from pedal_drill.model import Face
from pedal_drill.overview import OverviewCapsule, OverviewCircle, overview_features
from pedal_drill.parsers import NativeYamlParser, TaydaTxtParser
from pedal_drill.renderers.pdf import ReportLabPdfRenderer
from pedal_drill.renderers.styles import DETAIL_DRAWING_STYLE

_EXAMPLE = Path("tests/fixtures/native/example-layout.yaml")


def test_native_yaml_renders_to_pdf_with_unchanged_page_geometry(
    tmp_path: Path,
) -> None:
    document = NativeYamlParser().parse_document_file(_EXAMPLE)
    enclosure = EnclosureCatalog.built_in().get(document.enclosure_id)
    output = tmp_path / "native.pdf"

    pages = ReportLabPdfRenderer().render(document.template, enclosure, output)

    assert output.read_bytes().startswith(b"%PDF-")
    assert pages[0].is_overview
    assert (pages[0].width, pages[0].height) == (
        Decimal("200"),
        Decimal("269"),
    )
    face_a = enclosure.dimensions_for(Face.A)
    assert (pages[1].width, pages[1].height) == (
        face_a.width + Decimal("20"),
        face_a.height + Decimal("30"),
    )


def test_extension_dispatch_keeps_equivalent_tayda_holes() -> None:
    native = NativeYamlParser().parse_text(
        """format: pedal-drill-1
enclosure: hammond-1590bb
features:
  - type: hole
    face: A
    center: [0.1, -6.4]
    diameter: 7
"""
    )
    tayda = TaydaTxtParser().parse_text("A\t7\t0.1\t-6.4\n")

    assert native.holes == tayda.holes


def test_native_holes_use_existing_enclosure_validation() -> None:
    document = NativeYamlParser().parse_document(
        """format: pedal-drill-1
enclosure: hammond-1590bb
features:
  - type: hole
    face: A
    center: [100, 0]
    diameter: 7
"""
    )
    enclosure = EnclosureCatalog.built_in().get(document.enclosure_id)

    with pytest.raises(DrillLayoutOutsideEnclosureError):
        validate_template_fits_enclosure(document.template, enclosure)


def test_native_slots_use_the_canonical_capsule_geometry() -> None:
    slot = NativeYamlParser().parse_document_file(_EXAMPLE).template.slots[0]
    contour = capsule_path(
        capsule_for_slot(
            slot,
            EnclosureCatalog.built_in()
            .get("hammond-1590bb")
            .dimensions_for(Face.A),
            Decimal("10"),
            Decimal("20"),
        )
    )

    assert contour.first_end_arc.radius == Decimal("3")
    assert contour.second_end_arc.radius == Decimal("3")
    assert contour.is_closed


@pytest.mark.parametrize("drill_ends", [False, True])
def test_slot_end_guides_do_not_change_validation(drill_ends: bool) -> None:
    document = NativeYamlParser().parse_document_file(_EXAMPLE)
    slot = replace(document.template.slots[0], drill_ends=drill_ends)
    template = replace(document.template, slots=(slot,))

    validate_template_fits_enclosure(
        template, EnclosureCatalog.built_in().get(document.enclosure_id)
    )


def test_slot_without_drill_ends_draws_no_endpoint_guides() -> None:
    document = NativeYamlParser().parse_document_file(_EXAMPLE)
    slot = replace(document.template.slots[0], drill_ends=False)
    renderer = ReportLabPdfRenderer()

    with (
        patch.object(renderer, "_draw_capsule") as draw_capsule,
        patch.object(renderer, "_draw_circle_feature") as draw_circle,
    ):
        renderer._draw_slot(
            cast(Canvas, MagicMock()),
            slot,
            EnclosureCatalog.built_in()
            .get(document.enclosure_id)
            .dimensions_for(Face.A),
        )

    draw_capsule.assert_called_once()
    draw_circle.assert_not_called()


def test_rotated_slot_drill_ends_draw_two_guides_on_the_capsule_axis() -> None:
    document = NativeYamlParser().parse_document_file(_EXAMPLE)
    slot = document.template.slots[0]
    dimensions = (
        EnclosureCatalog.built_in()
        .get(document.enclosure_id)
        .dimensions_for(Face.A)
    )
    renderer = ReportLabPdfRenderer()
    expected_capsule = capsule_for_slot(
        slot,
        dimensions,
        renderer._margin,
        renderer._bottom_margin,
    )

    with (
        patch.object(renderer, "_draw_capsule"),
        patch.object(renderer, "_draw_circle_feature") as draw_circle,
    ):
        renderer._draw_slot(cast(Canvas, MagicMock()), slot, dimensions)

    assert tuple(call.args[1] for call in draw_circle.call_args_list) == (
        capsule_centerline_endpoints(expected_capsule)
    )
    assert tuple(call.args[2] for call in draw_circle.call_args_list) == (
        Decimal("3"),
        Decimal("3"),
    )
    assert all(
        call.args[3] is DETAIL_DRAWING_STYLE
        for call in draw_circle.call_args_list
    )


def test_endpoint_guides_do_not_become_overview_holes() -> None:
    template = NativeYamlParser().parse_document_file(_EXAMPLE).template
    features = overview_features(template, Face.A)

    assert sum(isinstance(feature, OverviewCapsule) for feature in features) == 1
    assert sum(isinstance(feature, OverviewCircle) for feature in features) == 1


def test_cli_uses_yaml_enclosure_and_preserves_txt_invocation(
    tmp_path: Path,
) -> None:
    yaml_output = tmp_path / "yaml.pdf"
    txt_input = tmp_path / "layout.txt"
    txt_output = tmp_path / "txt.pdf"
    txt_input.write_text("A\t7\t0\t0\n", encoding="utf-8")

    assert main(["render", str(_EXAMPLE), str(yaml_output)]) == 0
    assert (
        main(
            [
                "render",
                str(txt_input),
                "hammond-1590bb",
                str(txt_output),
            ]
        )
        == 0
    )
    assert yaml_output.exists()
    assert txt_output.exists()
