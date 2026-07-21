"""Input-format selection kept separate from individual parser schemas."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pedal_drill.model import DrillTemplate
from pedal_drill.parsers.base import ParseError
from pedal_drill.parsers.native_yaml import NativeYamlParser
from pedal_drill.parsers.tayda_txt import TaydaTxtParser


@dataclass(frozen=True, slots=True)
class ParsedTemplateInput:
    """A parsed template and an optional format-provided enclosure ID."""

    template: DrillTemplate
    enclosure_id: str | None


def parse_input_file(path: Path) -> ParsedTemplateInput:
    """Select a parser strictly from the input filename extension."""

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return ParsedTemplateInput(TaydaTxtParser().parse_file(path), None)
    if suffix in (".yaml", ".yml"):
        document = NativeYamlParser().parse_document_file(path)
        return ParsedTemplateInput(document.template, document.enclosure_id)
    raise ParseError(
        f"Unsupported input extension {path.suffix!r}; expected .txt, .yaml, or .yml."
    )
