"""Command-line interface for pedal-drill."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from pedal_drill.parsers import ParseError, TaydaTxtParser


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""

    parser = argparse.ArgumentParser(prog="pedal-drill")
    subcommands = parser.add_subparsers(dest="command", required=True)
    inspect_command = subcommands.add_parser("inspect", help="Validate and summarize a Tayda TXT export.")
    inspect_command.add_argument("input", type=Path, help="Path to a Tayda TXT export.")
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
        print(f"{template.name}: {len(template.holes)} hole(s) imported from {template.source_format}")
        return 0
    return 1
