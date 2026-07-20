"""Allow ``python -m pedal_drill`` to run the command-line interface."""

from pedal_drill.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
