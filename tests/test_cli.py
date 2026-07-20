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
