from pathlib import Path

from pytest import CaptureFixture

from pedal_drill.cli import main


def test_inspect_reports_imported_holes(
    tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    export = tmp_path / "test.txt"
    export.write_text("A\t9\t0\t0\n", encoding="utf-8")

    assert main(["inspect", str(export)]) == 0
    assert "1 hole(s)" in capsys.readouterr().out


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
