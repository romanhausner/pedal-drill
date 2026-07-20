"""Command-line interface for pedal-drill."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.enclosures.validation import DrillLayoutOutsideEnclosureError
from pedal_drill.parsers import ParseError, TaydaTxtParser
from pedal_drill.renderers import PdfRenderError, ReportLabPdfRenderer


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(prog="pedal-drill")
    subcommands = parser.add_subparsers(dest="command", required=True)
    inspect_command = subcommands.add_parser(
        "inspect", help="Validate and summarize a Tayda TXT export."
    )
    inspect_command.add_argument("input", type=Path, help="Path to a Tayda TXT export.")
    render_command = subcommands.add_parser(
        "render", help="Render a Tayda TXT export as a 1:1 PDF."
    )
    render_command.add_argument("input", type=Path, help="Path to a Tayda TXT export.")
    render_command.add_argument("enclosure", help="Built-in enclosure identifier.")
    render_command.add_argument("output", type=Path, help="Destination PDF path.")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit status."""

    args = build_parser().parse_args(arguments)
    if args.command == "inspect":
        try:
            template = TaydaTxtParser().parse_file(args.input)
        except ParseError as error:
            print(f"pedal-drill: {error}")
            return 2
        print(
            f"{template.name}: {len(template.holes)} hole(s) "
            f"imported from {template.source_format}"
        )
        return 0
    if args.command == "render":
        try:
            template = TaydaTxtParser().parse_file(args.input)
            enclosure = EnclosureCatalog.built_in().get(args.enclosure)
            pages = ReportLabPdfRenderer().render(template, enclosure, args.output)
        except (
            KeyError,
            ParseError,
            PdfRenderError,
            DrillLayoutOutsideEnclosureError,
        ) as error:
            print(f"pedal-drill: {error}")
            return 2
        print(f"{args.output}: rendered {len(pages)} page(s)")
        return 0
    return 1
