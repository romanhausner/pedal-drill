"""Common contracts for external template parsers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pedal_drill.model import DrillTemplate


class ParseError(ValueError):
    """Raised when an external template cannot be converted safely."""


class TemplateParser(Protocol):
    """A parser that adapts one external representation into the domain model."""

    def parse_text(self, text: str, *, name: str | None = None) -> DrillTemplate:
        """Parse template text."""

    def parse_file(self, path: Path) -> DrillTemplate:
        """Parse UTF-8 template text from *path*."""
