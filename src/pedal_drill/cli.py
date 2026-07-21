"""Command-line interface for pedal-drill."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Callable, Sequence

from pedal_drill.enclosures import EnclosureCatalog
from pedal_drill.enclosures.model import EnclosureDefinition
from pedal_drill.enclosures.validation import DrillLayoutOutsideEnclosureError
from pedal_drill.model import Face
from pedal_drill.parsers import ParseError, parse_input_file
from pedal_drill.renderers import PdfRenderError, ReportLabPdfRenderer

CommandHandler = Callable[[argparse.Namespace], int]


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(prog="pedal-drill")
    subcommands = parser.add_subparsers(dest="command", required=True)
    inspect_command = subcommands.add_parser(
        "inspect", help="Validate and summarize a Tayda TXT or native YAML input."
    )
    inspect_command.add_argument(
        "input", type=Path, help="Path to a Tayda .txt or pedal-drill .yaml file."
    )
    inspect_command.set_defaults(handler=_inspect)

    render_command = subcommands.add_parser(
        "render", help="Render a Tayda TXT or native YAML input as a 1:1 PDF."
    )
    render_command.add_argument(
        "input", type=Path, help="Path to a Tayda .txt or pedal-drill .yaml file."
    )
    render_command.add_argument(
        "enclosure_or_output",
        help=(
            "Built-in enclosure ID for TXT input, or destination PDF for YAML input."
        ),
    )
    render_command.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Destination PDF path when an enclosure ID is supplied.",
    )
    render_command.set_defaults(handler=_render)

    list_command = subcommands.add_parser(
        "list-enclosures", help="List built-in enclosure definitions."
    )
    list_command.set_defaults(handler=_list_enclosures)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit status."""

    args = build_parser().parse_args(arguments)
    handler: CommandHandler = args.handler
    return handler(args)


def _inspect(args: argparse.Namespace) -> int:
    try:
        parsed = parse_input_file(args.input)
        if parsed.enclosure_id is not None:
            EnclosureCatalog.built_in().get(parsed.enclosure_id)
        template = parsed.template
    except (KeyError, ParseError) as error:
        print(f"pedal-drill: {error}")
        return 2
    print(
        f"{template.name}: {len(template.holes)} hole(s) "
        f"imported from {template.source_format}"
    )
    return 0


def _render(args: argparse.Namespace) -> int:
    try:
        parsed = parse_input_file(args.input)
        enclosure_id, output = _render_targets(args, parsed.enclosure_id)
        enclosure = EnclosureCatalog.built_in().get(enclosure_id)
        pages = ReportLabPdfRenderer().render(parsed.template, enclosure, output)
    except (
        KeyError,
        ParseError,
        PdfRenderError,
        DrillLayoutOutsideEnclosureError,
    ) as error:
        print(f"pedal-drill: {error}")
        return 2
    print(f"{output}: rendered {len(pages)} page(s)")
    return 0


def _render_targets(
    args: argparse.Namespace, embedded_enclosure_id: str | None
) -> tuple[str, Path]:
    """Resolve backward-compatible TXT and enclosure-owning YAML arguments."""

    if embedded_enclosure_id is None:
        if args.output is None:
            raise ParseError(
                "TXT rendering requires: input, enclosure ID, and output PDF."
            )
        return args.enclosure_or_output, args.output

    if args.output is None:
        return embedded_enclosure_id, Path(args.enclosure_or_output)
    if args.enclosure_or_output != embedded_enclosure_id:
        raise ParseError(
            f"YAML selects enclosure {embedded_enclosure_id!r}, but command line "
            f"specified {args.enclosure_or_output!r}."
        )
    return embedded_enclosure_id, args.output


def _list_enclosures(_: argparse.Namespace) -> int:
    rows = [
        _enclosure_row(enclosure)
        for enclosure in EnclosureCatalog.built_in().all()
    ]
    headers = ("ID", "Manufacturer", "Model", "Face A")
    widths = tuple(
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    )
    print(_format_row(headers, widths))
    print("-" * (sum(widths) + (3 * (len(widths) - 1))))
    for row in rows:
        print(_format_row(row, widths))
    return 0


def _face_dimensions(width: Decimal, height: Decimal) -> str:
    return f"{width} × {height} mm"


def _enclosure_row(enclosure: EnclosureDefinition) -> tuple[str, str, str, str]:
    face = enclosure.dimensions_for(Face.A)
    return (
        enclosure.identifier,
        enclosure.manufacturer,
        enclosure.model,
        _face_dimensions(face.width, face.height),
    )


def _format_row(row: tuple[str, ...], widths: tuple[int, ...]) -> str:
    cells = (
        value.ljust(width) for value, width in zip(row, widths, strict=True)
    )
    return " | ".join(cells)
