# pedal-drill

`pedal-drill` is a command-line tool for generating printable 1:1 drill
templates for guitar-pedal enclosures from Tayda Electronics drill-template
exports.

It parses Tayda's unheadered TXT format, validates the complete feature geometry
against a selected enclosure definition, and renders a PDF containing:

- an unfolded enclosure overview
- one 1:1 page for each populated face
- enclosure outlines
- circular holes
- slots and compound elongated shapes
- construction lines
- horizontal and vertical calibration lines
- printing instructions

Enclosure dimensions are stored in JSON files. Rectangular and tapered side
faces are supported. Several bundled Hammond definitions use trapezoid
dimensions derived from the manufacturer's CAD models.

## Requirements

- Python 3.13 or newer

## Development installation

```console
git clone https://github.com/romanhausner/pedal-drill
cd pedal-drill
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
```

## Usage

### Inspect a Tayda export

```console
pedal-drill inspect path/to/template.txt
```

This parses the file and reports its contents without generating a PDF.

### List built-in enclosures

```console
pedal-drill list-enclosures
```

### Render a PDF

```console
pedal-drill render \
    path/to/template.txt \
    hammond-1590xx \
    output/template.pdf
```

The output begins with an orientation overview of the unfolded enclosure.
Each populated face then receives its own page at 1:1 scale.

When printing:

- use 100% scale
- disable “Fit to page” or similar scaling
- verify both calibration lines before drilling

## Built-in enclosure models

The following enclosure definitions are currently included:

```text
ID              | Manufacturer          | Model   | Face A
--------------------------------------------------------------------
hammond-1550b   | Hammond               | 1550B   | 64.0 × 114.5 mm
hammond-1590a   | Hammond Manufacturing | 1590A   | 38.5 × 92.6 mm
hammond-1590b   | Hammond Manufacturing | 1590B   | 60.5 × 112.4 mm
hammond-1590b2  | Hammond Manufacturing | 1590B2  | 60.5 × 112.4 mm
hammond-1590b3  | Hammond Manufacturing | 1590B3  | 77.0 × 116.0 mm
hammond-1590bb  | Hammond Manufacturing | 1590BB  | 94.0 × 119.5 mm
hammond-1590bb2 | Hammond Manufacturing | 1590BB2 | 94.0 × 119.5 mm
hammond-1590g   | Hammond               | 1590G   | 50.0 × 100.0 mm
hammond-1590x   | Hammond               | 1590X   | 121.2 × 145.2 mm
hammond-1590xx  | Hammond Manufacturing | 1590XX  | 121.2 × 145.2 mm
```

The same list can be printed from the installed application with
`pedal-drill list-enclosures`.

## Tayda TXT input

The parser accepts the unheadered, tab-delimited TXT export produced by the
Tayda drilling configurator.

Circle records contain:

```text
face    diameter    x    y
```

For example:

```text
A	9	0	20
A	12	0	-35
B	10	0	0
```

The values are:

- enclosure face
- diameter in millimetres
- horizontal coordinate
- vertical coordinate

Faces `A` through `E` use Tayda's enclosure-face convention. Coordinates remain
in Tayda's centre-of-face coordinate system.

Line records are retained as construction geometry and are also used when
recognizing compound elongated shapes made from two circles and two connecting
lines.

Blank lines and lines beginning with `#` are ignored. Invalid records are
reported with their input line number.

## Enclosure definitions

Built-in enclosure definitions are stored as JSON files under:

```text
src/pedal_drill/enclosures/definitions/
```

Every definition contains all five Tayda faces and declares its dimensions in
millimetres.

A rectangular face uses:

```json
{
  "width": 100,
  "height": 120
}
```

Rectangle is the default shape, so no explicit `shape` property is required.

A centred symmetric trapezoid uses:

```json
{
  "shape": "trapezoid",
  "top_width": 119.36,
  "bottom_width": 121.20,
  "height": 35.20
}
```

For trapezoidal side faces:

- `top_width` is the edge adjacent to the closed Face A surface
- `bottom_width` is the edge adjacent to the open or lid side
- `height` is the enclosure-body height
- the face origin remains at its geometric centre

The trapezoid describes the useful drilling-face envelope. Casting fillets,
rounded body transitions, wall thickness, lid lips and internal details are not
part of this geometry.

For CAD-derived definitions, the side-face height excludes the removable lid
and any part of the lid projecting beyond the enclosure body.

## Validation

Before rendering, the complete feature geometry is checked against the selected
face outline.

Validation covers:

- circular holes
- rounded slots
- construction lines
- rectangular faces
- trapezoidal faces with sloped boundaries

A feature is rejected when any part of it extends beyond the usable face
outline. This includes cases where a feature remains inside the rectangular
bounding box but crosses a sloped trapezoid edge.

## PDF output

The PDF renderer uses the normalized domain model and enclosure geometry.

The overview page shows all five faces as an outside-view enclosure net.
Populated faces are highlighted and their features are drawn at a reduced
scale.

The detail pages retain drilling aids such as:

- hole crosshairs
- diameter labels
- construction lines
- calibration references

Trapezoidal side faces are rendered with rounded visual corners while
validation continues to use their defined drilling envelope.

## Project structure

```text
src/pedal_drill/
├── cli.py
├── model.py
├── geometry/
├── enclosures/
│   ├── definitions/
│   └── validation.py
├── parsers/
├── overview/
└── renderers/
```

The main responsibilities are separated as follows:

- `model.py` contains immutable, format-independent drill-template objects.
- `parsers/` converts external input into the domain model.
- `enclosures/` loads enclosure definitions and validates layouts.
- `geometry/` contains reusable face, polygon and feature geometry.
- `overview/` prepares simplified geometry for the unfolded overview.
- `renderers/` produces output from the normalized model.
- `cli.py` provides the command-line interface.

## CAD analysis tooling

Optional tooling under `tools/` can analyze STEP and IGES enclosure assemblies
with CadQuery and OpenCascade.

It is separate from the normal application runtime:

```console
python3.12 -m venv .venv-cad
. .venv-cad/bin/activate
python -m pip install -r tools/requirements-cad.txt
```

Example:

```console
python tools/analyze_enclosure_cad.py \
    path/to/1590XX.stp \
    --nominal 145 121 39
```

The analyzer identifies the enclosure body and removable lid, measures multiple
cross-sections through the drafted walls, and reports proposed trapezoid
dimensions.

Reviewed analysis reports are stored under:

```text
docs/cad-analysis/
```

The original CAD files are not required for normal use.

## Tests

```console
python -m pytest
```

## License

MIT. See [LICENSE](LICENSE).
