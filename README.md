# pedal-drill

`pedal-drill` is an open-source command-line tool for making printable, 1:1
drill templates for guitar-pedal enclosures.  Its first input is the TXT
export from the Tayda Electronics drilling configurator. Future releases will
render PDF, SVG, and DXF output.

This first milestone deliberately stops at import and validation: it provides
a stable, format-neutral domain model and a Tayda TXT parser, but does not yet
create PDF files.

## Requirements

- Python 3.13 or newer

The application has no runtime dependencies. Development tests use `pytest`.

## Install for development

```console
git clone <repository-url>
cd pedal-drill
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
```

## Inspect a Tayda export

```console
pedal-drill inspect path/to/template.txt
```

Render a 1:1 PDF using a built-in enclosure definition:

```console
pedal-drill render path/to/template.txt hammond-1590xx output/template.pdf
```

The Tayda parser accepts the tool's unheadered, tab-delimited export.
Coordinates and diameters are in millimetres; the Tayda centre-of-face
coordinate system is retained unchanged.

```text
A\t9\t0\t20
A\t12\t0\t-35
B\t10\t0\t0
```

The four values are `side`, `diameter`, `x`, and `y`. `A` through `E` identify
Tayda's enclosure faces. Tayda line records are retained too. Blank lines and
lines starting with `#` are ignored. The parser reports the precise input line
for invalid records.

## Architecture

- `model.py` holds format- and renderer-independent immutable domain objects.
- `enclosures/definitions/` contains JSON geometry definitions. The catalog
  makes physical dimensions available to future renderers without hardcoding
  them in Python. Each file declares one `unit`; values are normalized to the
  application's millimetre base unit when loaded.
- `renderers/pdf.py` converts the normalized model to a basic 1:1 PDF using
  ReportLab. SVG and DXF renderers can use the same model later.

An enclosure definition is intentionally small and uses JSON numbers for all
dimensions:

```json
{
  "id": "example-enclosure",
  "manufacturer": "Example",
  "model": "Example 1",
  "unit": "mm",
  "faces": {
    "A": { "width": 100, "height": 120 }
  }
}
```

Rectangle is the default face shape, so existing definitions do not need a
`shape` property. A centred symmetric trapezoid can be declared explicitly:

```json
{
  "shape": "trapezoid",
  "top_width": 119.36,
  "bottom_width": 121.20,
  "height": 35.20
}
```

For trapezoids, `top_width` is the edge adjacent to the closed Face A surface
and `bottom_width` is adjacent to the open/lid side. The face origin remains at
the geometric centre. These dimensions describe the useful drilling-face
envelope; casting fillets, rounded body transitions and the lid lip are not
represented by the trapezoid.

All five Tayda faces must be present. `mm` is currently the only accepted
source unit; the unit declaration and loader boundary make future conversions
possible without altering this JSON schema.
- `parsers/` turns external formats into the domain model. Each parser shares
  the small `TemplateParser` protocol, so other import formats can be added
  without touching renderers.
- `renderers/` is the future home of PDF, SVG, and DXF emitters. It is kept
  separate from parsing and intentionally contains no implementation yet.
- `cli.py` is a thin command-line adapter.

## Test

```console
python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
