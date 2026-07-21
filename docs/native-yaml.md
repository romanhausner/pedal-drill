# Native YAML format

The `pedal-drill-1` format describes drilling features independently of any
renderer. It maps holes, capsule slots, and construction lines onto the same
domain model used by Tayda TXT imports.

## Complete example

```yaml
format: pedal-drill-1
enclosure: hammond-1590bb
unit: mm

features:
  - type: hole
    face: A
    center: [0, 30]
    diameter: 7

  - type: slot
    face: A
    center: [20, -10]
    length: 18
    width: 6
    angle: 30
    drill_ends: true

  - type: hole
    face: C
    center: [10, 0]
    diameter: 9

  - type: line
    face: C
    from: [-10, -15]
    to: [10, -15]
```

The same example is available as
[`examples/native-1590bb.yaml`](../examples/native-1590bb.yaml).

## Coordinates

Each face has an independent, centre-origin coordinate system:

```text
                 +y
                  ^
                  |
                  |
       -x <-------+-------> +x
                  | (0, 0)
                  |
                  v
                 -y
```

Each face uses its own local coordinate system. Viewed directly from outside
the enclosure, x increases to the right and y increases upward. The origin is
the centre of the face. This convention applies identically to faces A through
E. The unfolded overview performs its own rotations without changing the input
coordinate meaning.

Coordinates and dimensions are millimetres. `unit` may be omitted; when it is
present, it must be `mm`.

## Root fields

- `format` is required and must be `pedal-drill-1`.
- `enclosure` is required and must identify a built-in enclosure.
- `features` is required and must be a list.
- `unit` is optional and currently supports only `mm`.

Unknown fields and duplicate mapping keys are rejected.

## Circular holes

```yaml
- type: hole
  face: A
  center: [0, 30]
  diameter: 7
```

`diameter` must be greater than zero.

## Capsule slots

```yaml
- type: slot
  face: A
  center: [20, -10]
  length: 18
  width: 6
  angle: 30
  drill_ends: true
```

A slot is a capsule with two parallel sides and two semicircular ends.
`length` is its total outside length, including the rounded ends. `width` is
the total slot width and the diameter of each semicircular end. Length must be
at least width.

`angle` is measured counter-clockwise in degrees from the positive x-axis. It
defaults to `0`; `90` produces a vertical slot. Negative angles are accepted.

`drill_ends` defaults to `false`. When enabled, the 1:1 detail page adds a
crosshaired drill circle at each end centre. Each guide diameter equals the
slot width. This is a fabrication aid only: it does not change the cutout
geometry, validation, populated-face count, or overview rendering.

## Construction lines

```yaml
- type: line
  face: C
  from: [-10, -15]
  to: [10, -15]
```

The start and end points must be different.

## CLI usage

The parser is selected by extension. `.yaml` and `.yml` use this format; `.txt`
continues to use the Tayda parser.

```console
pedal-drill inspect examples/native-1590bb.yaml
pedal-drill render examples/native-1590bb.yaml output/native-1590bb.pdf
```

The YAML document supplies the enclosure identifier, so the render command
does not require a separate enclosure argument.
