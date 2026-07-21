from pathlib import Path

import pytest
from pytest import CaptureFixture

from pedal_drill.cli import build_parser, main


def test_inspect_reports_imported_holes(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    export = tmp_path / "test.txt"
    export.write_text("A\t9\t0\t0\n", encoding="utf-8")

    assert main(["inspect", str(export)]) == 0
    assert "1 hole(s)" in capsys.readouterr().out


def test_inspect_accepts_native_yaml(capsys: CaptureFixture[str]) -> None:
    assert main(["inspect", "tests/fixtures/native/example-layout.yaml"]) == 0

    output = capsys.readouterr().out
    assert "2 hole(s)" in output
    assert "pedal-drill-1" in output


def test_render_help_advertises_txt_and_yaml(
    capsys: CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["render", "--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "Tayda .txt" in help_text
    assert "pedal-drill .yaml" in help_text


def test_inspect_rejects_unknown_native_enclosure(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    layout = tmp_path / "unknown.yaml"
    layout.write_text(
        """format: pedal-drill-1
enclosure: hammond-does-not-exist
features: []
""",
        encoding="utf-8",
    )

    assert main(["inspect", str(layout)]) == 2
    assert "hammond-does-not-exist" in capsys.readouterr().out


def test_render_reports_an_outside_feature_without_creating_pdf(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    export = tmp_path / "outside.txt"
    output = tmp_path / "outside.pdf"
    export.write_text("A\t10\t30\t0\n", encoding="utf-8")

    assert main(["render", str(export), "hammond-1590b", str(output)]) == 2

    error = capsys.readouterr().out
    assert "hammond-1590b" in error
    assert "face A" in error
    assert "circular hole" in error
    assert "right" in error
    assert "The drill layout does not fit this enclosure." in error
    assert not output.exists()


def test_list_enclosures_prints_alphabetical_catalog(
    capsys: CaptureFixture[str],
) -> None:
    assert main(["list-enclosures"]) == 0

    lines = capsys.readouterr().out.splitlines()
    data_rows = lines[2:]
    identifiers = [row.split(" | ", maxsplit=1)[0].strip() for row in data_rows]

    assert lines[0].startswith("ID")
    assert "Manufacturer" in lines[0]
    assert "Face A" in lines[0]
    assert identifiers == sorted(identifiers)
    row_1590a = next(row for row in data_rows if "hammond-1590a" in row)
    assert "Hammond Manufacturing" in row_1590a
    assert "38.5 × 92.6 mm" in row_1590a
    assert any("hammond-1590g" in row for row in data_rows)
    assert any("hammond-1590x" in row for row in data_rows)
    assert any("hammond-1550b" in row for row in data_rows)
