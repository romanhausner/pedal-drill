#!/usr/bin/env python3
"""Measure a tapered enclosure body from a STEP or IGES assembly.

CadQuery/OpenCascade is imported only when CAD analysis is requested.  The
normal pedal-drill runtime therefore remains independent of a CAD kernel.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Sequence


class CadAnalysisError(RuntimeError):
    """Raised when reliable enclosure measurements cannot be produced."""


@dataclass(frozen=True, slots=True)
class Taper:
    """The total and per-side change between parallel trapezoid edges."""

    difference: float
    side_offset: float


@dataclass(frozen=True, slots=True)
class SectionPlanes:
    """Interior section coordinates near the closed and open body levels."""

    near_closed: float
    near_open: float


@dataclass(frozen=True, slots=True)
class SectionMeasurement:
    """Outer-contour measurements at one section plane."""

    coordinate: float
    length: float
    width: float
    length_center: float
    width_center: float
    corner_radius: float | None


@dataclass(frozen=True, slots=True)
class LinearFit:
    """A least-squares line and coefficient of determination."""

    slope: float
    intercept: float
    r_squared: float

    def at(self, coordinate: float) -> float:
        """Evaluate the fitted line at *coordinate*."""

        return self.slope * coordinate + self.intercept


@dataclass(frozen=True, slots=True)
class SolidSummary:
    """Diagnostic properties used to distinguish assembly components."""

    index: int
    volume: float
    dimensions: tuple[float, float, float]
    center: tuple[float, float, float]
    face_count: int


@dataclass(frozen=True, slots=True)
class CadAnalysis:
    """Complete body and section analysis, expressed in millimetres."""

    source: Path
    backend: str
    units: str
    product_names: tuple[str, ...]
    solids: tuple[SolidSummary, ...]
    unique_geometry_count: int
    body_index: int
    lid_index: int
    height_axis: str
    length_axis: str
    width_axis: str
    closed_coordinate: float
    open_coordinate: float
    body_height: float
    lid_height: float
    lid_projection: float
    near_closed: SectionMeasurement
    near_open: SectionMeasurement
    top_length: float
    bottom_length: float
    top_width: float
    bottom_width: float
    length_fit_r_squared: float
    width_fit_r_squared: float
    length_draft_degrees: float
    width_draft_degrees: float
    symmetry_deviation: float
    corner_radius: float | None


def trapezoid_taper(top: float, bottom: float) -> Taper:
    """Return total taper and the offset of each centred trapezoid side."""

    if top <= 0 or bottom <= 0:
        raise ValueError("Trapezoid edge dimensions must be positive.")
    difference = bottom - top
    return Taper(difference=difference, side_offset=difference / 2)


def choose_section_planes(
    closed_coordinate: float,
    open_coordinate: float,
    offset: float,
) -> SectionPlanes:
    """Choose two interior planes while supporting either body-axis direction."""

    if offset <= 0:
        raise ValueError("The section offset must be positive.")
    span = abs(open_coordinate - closed_coordinate)
    if span <= 2 * offset:
        raise ValueError("The body is too shallow for the requested section offset.")
    direction = 1.0 if open_coordinate > closed_coordinate else -1.0
    return SectionPlanes(
        near_closed=closed_coordinate + direction * offset,
        near_open=open_coordinate - direction * offset,
    )


def proposed_face_json(
    *,
    top_length: float,
    bottom_length: float,
    top_width: float,
    bottom_width: float,
    body_height: float,
) -> dict[str, dict[str, dict[str, float | str]]]:
    """Build pedal-drill's proposed A--E side-face trapezoid fragment."""

    def face(top: float, bottom: float) -> dict[str, float | str]:
        return {
            "shape": "trapezoid",
            "top_width": round(top, 2),
            "bottom_width": round(bottom, 2),
            "height": round(body_height, 2),
        }

    return {
        "faces": {
            "B": face(top_width, bottom_width),
            "C": face(top_length, bottom_length),
            "D": face(top_width, bottom_width),
            "E": face(top_length, bottom_length),
        }
    }


def linear_fit(samples: Sequence[tuple[float, float]]) -> LinearFit:
    """Fit a line without requiring NumPy in pure-geometry tests."""

    if len(samples) < 2:
        raise ValueError("At least two samples are required for a linear fit.")
    mean_x = sum(x for x, _ in samples) / len(samples)
    mean_y = sum(y for _, y in samples) / len(samples)
    denominator = sum((x - mean_x) ** 2 for x, _ in samples)
    if denominator == 0:
        raise ValueError("Section coordinates must not all be identical.")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in samples) / denominator
    intercept = mean_y - slope * mean_x
    residual = sum((y - (slope * x + intercept)) ** 2 for x, y in samples)
    total = sum((y - mean_y) ** 2 for _, y in samples)
    r_squared = 1.0 if total == 0 else 1.0 - residual / total
    return LinearFit(slope, intercept, r_squared)


def analyze_cad(path: Path, *, section_offset: float = 1.2) -> CadAnalysis:
    """Load an assembly, isolate its body, and measure its drafted outer wall."""

    shape, backend = _load_cad(path)
    solids = tuple(shape.Solids())
    if not solids:
        raise CadAnalysisError("No valid solid was found in the CAD file.")
    summaries = tuple(
        _solid_summary(index, solid) for index, solid in enumerate(solids)
    )
    body_index, lid_index = _identify_body_and_lid(summaries)
    body = solids[body_index]
    lid = solids[lid_index]
    body_box = body.BoundingBox()
    lid_box = lid.BoundingBox()
    axes = _axis_interpretation(body_box)
    height_index, length_index, width_index = axes
    body_limits = _axis_limits(body_box, height_index)
    lid_center = summaries[lid_index].center[height_index]
    body_center = summaries[body_index].center[height_index]
    if lid_center > body_center:
        closed_coordinate, open_coordinate = body_limits
    else:
        open_coordinate, closed_coordinate = body_limits
    planes = choose_section_planes(
        closed_coordinate,
        open_coordinate,
        section_offset,
    )
    coordinates = _sample_coordinates(planes.near_closed, planes.near_open, 9)
    measurements = tuple(
        _measure_section(
            body,
            coordinate,
            height_index,
            length_index,
            width_index,
        )
        for coordinate in coordinates
    )
    length_fit = linear_fit(
        [(item.coordinate, item.length) for item in measurements]
    )
    width_fit = linear_fit([(item.coordinate, item.width) for item in measurements])
    if min(length_fit.r_squared, width_fit.r_squared) < 0.999:
        raise CadAnalysisError(
            "Usable linear outer-wall sections could not be calculated reliably."
        )
    near_closed = measurements[0]
    near_open = measurements[-1]
    top_length = length_fit.at(closed_coordinate)
    bottom_length = length_fit.at(open_coordinate)
    top_width = width_fit.at(closed_coordinate)
    bottom_width = width_fit.at(open_coordinate)
    direction = 1.0 if open_coordinate > closed_coordinate else -1.0
    length_side_slope = length_fit.slope * direction / 2
    width_side_slope = width_fit.slope * direction / 2
    body_height = abs(open_coordinate - closed_coordinate)
    lid_limits = _axis_limits(lid_box, height_index)
    lid_height = abs(lid_limits[1] - lid_limits[0])
    lid_projection = (
        max(lid_limits) - open_coordinate
        if direction > 0
        else open_coordinate - min(lid_limits)
    )
    length_centers = [item.length_center for item in measurements]
    width_centers = [item.width_center for item in measurements]
    symmetry_deviation = max(
        max(length_centers) - min(length_centers),
        max(width_centers) - min(width_centers),
    )
    radii = [item.corner_radius for item in measurements if item.corner_radius]
    return CadAnalysis(
        source=path,
        backend=backend,
        units=_detect_units(path),
        product_names=_step_product_names(path),
        solids=summaries,
        unique_geometry_count=_unique_geometry_count(summaries),
        body_index=body_index,
        lid_index=lid_index,
        height_axis=_AXIS_NAMES[height_index],
        length_axis=_AXIS_NAMES[length_index],
        width_axis=_AXIS_NAMES[width_index],
        closed_coordinate=closed_coordinate,
        open_coordinate=open_coordinate,
        body_height=body_height,
        lid_height=lid_height,
        lid_projection=lid_projection,
        near_closed=near_closed,
        near_open=near_open,
        top_length=top_length,
        bottom_length=bottom_length,
        top_width=top_width,
        bottom_width=bottom_width,
        length_fit_r_squared=length_fit.r_squared,
        width_fit_r_squared=width_fit.r_squared,
        length_draft_degrees=math.degrees(math.atan(abs(length_side_slope))),
        width_draft_degrees=math.degrees(math.atan(abs(width_side_slope))),
        symmetry_deviation=symmetry_deviation,
        corner_radius=median(radii) if radii else None,
    )


_AXIS_NAMES = ("X", "Y", "Z")


def _load_cad(path: Path) -> tuple[Any, str]:
    if not path.is_file():
        raise CadAnalysisError(f"CAD file does not exist: {path}")
    try:
        import cadquery as cq
    except ImportError as error:
        raise CadAnalysisError(
            "No CAD backend is available. Install tools/requirements-cad.txt."
        ) from error
    try:
        suffix = path.suffix.lower()
        if suffix in {".step", ".stp"}:
            return cq.importers.importStep(str(path)).val(), "CadQuery/OpenCascade"
        if suffix in {".iges", ".igs"}:
            from OCP.IFSelect import IFSelect_RetDone
            from OCP.IGESControl import IGESControl_Reader

            reader = IGESControl_Reader()
            if reader.ReadFile(str(path)) != IFSelect_RetDone:
                raise CadAnalysisError(f"OpenCascade could not read IGES file: {path}")
            reader.TransferRoots()
            return cq.Shape.cast(reader.OneShape()), "CadQuery/OpenCascade (IGES)"
        if suffix in {".x_t", ".x_b"}:
            raise CadAnalysisError(
                "The installed OpenCascade backend cannot read Parasolid files; "
                "use the STEP or IGES version."
            )
        raise CadAnalysisError(f"Unsupported CAD file extension: {suffix or '(none)'}")
    except CadAnalysisError:
        raise
    except Exception as error:
        raise CadAnalysisError(f"CAD file could not be loaded: {error}") from error


def _solid_summary(index: int, solid: Any) -> SolidSummary:
    box = solid.BoundingBox()
    center = solid.Center().toTuple()
    return SolidSummary(
        index=index,
        volume=float(solid.Volume()),
        dimensions=(float(box.xlen), float(box.ylen), float(box.zlen)),
        center=tuple(float(value) for value in center),
        face_count=len(solid.Faces()),
    )


def _identify_body_and_lid(summaries: Sequence[SolidSummary]) -> tuple[int, int]:
    if len(summaries) < 2:
        raise CadAnalysisError(
            "The enclosure body cannot be distinguished from a removable lid."
        )
    body = max(summaries, key=lambda item: item.volume)
    height_index = min(range(3), key=lambda axis: body.dimensions[axis])
    plan_axes = [axis for axis in range(3) if axis != height_index]
    candidates: list[SolidSummary] = []
    for item in summaries:
        if item.index == body.index:
            continue
        plan_ratios = [
            item.dimensions[axis] / body.dimensions[axis] for axis in plan_axes
        ]
        if (
            all(0.85 <= ratio <= 1.15 for ratio in plan_ratios)
            and item.dimensions[height_index] < body.dimensions[height_index] * 0.5
            and item.volume > body.volume * 0.05
        ):
            candidates.append(item)
    if len(candidates) != 1:
        raise CadAnalysisError(
            "The enclosure body cannot be distinguished unambiguously from the lid."
        )
    return body.index, candidates[0].index


def _axis_interpretation(box: Any) -> tuple[int, int, int]:
    dimensions = (float(box.xlen), float(box.ylen), float(box.zlen))
    height = min(range(3), key=lambda axis: dimensions[axis])
    plan = [axis for axis in range(3) if axis != height]
    length = max(plan, key=lambda axis: dimensions[axis])
    width = next(axis for axis in plan if axis != length)
    if dimensions[height] >= dimensions[width] * 0.75:
        raise CadAnalysisError("The enclosure body height axis is ambiguous.")
    return height, length, width


def _axis_limits(box: Any, axis: int) -> tuple[float, float]:
    return (
        (float(box.xmin), float(box.xmax)),
        (float(box.ymin), float(box.ymax)),
        (float(box.zmin), float(box.zmax)),
    )[axis]


def _measure_section(
    body: Any,
    coordinate: float,
    height_axis: int,
    length_axis: int,
    width_axis: int,
) -> SectionMeasurement:
    import cadquery as cq

    normal = tuple(1.0 if axis == height_axis else 0.0 for axis in range(3))
    x_direction = tuple(1.0 if axis == length_axis else 0.0 for axis in range(3))
    plane = cq.Plane(origin=(0, 0, 0), xDir=x_direction, normal=normal)
    try:
        section = cq.Workplane(plane).newObject([body]).section(coordinate).val()
        wires = section.Wires()
    except Exception as error:
        raise CadAnalysisError(
            f"Cross-section at {coordinate:.3f} mm could not be calculated: {error}"
        ) from error
    if not wires:
        raise CadAnalysisError(
            f"Cross-section at {coordinate:.3f} mm has no usable contour."
        )
    outer = max(wires, key=lambda wire: wire.Length())
    box = outer.BoundingBox()
    length_limits = _axis_limits(box, length_axis)
    width_limits = _axis_limits(box, width_axis)
    corner_candidates: list[float] = []
    for edge in outer.Edges():
        if edge.geomType() not in {"CIRCLE", "ELLIPSE"}:
            continue
        edge_box = edge.BoundingBox()
        first = _axis_limits(edge_box, length_axis)
        second = _axis_limits(edge_box, width_axis)
        extents = (first[1] - first[0], second[1] - second[0])
        if min(extents) > 0 and abs(extents[0] - extents[1]) <= 0.05:
            corner_candidates.append(sum(extents) / 2)
    return SectionMeasurement(
        coordinate=coordinate,
        length=length_limits[1] - length_limits[0],
        width=width_limits[1] - width_limits[0],
        length_center=sum(length_limits) / 2,
        width_center=sum(width_limits) / 2,
        corner_radius=median(corner_candidates) if corner_candidates else None,
    )


def _sample_coordinates(start: float, end: float, count: int) -> tuple[float, ...]:
    if count < 2:
        raise ValueError("At least two section samples are required.")
    return tuple(start + (end - start) * index / (count - 1) for index in range(count))


def _unique_geometry_count(summaries: Sequence[SolidSummary]) -> int:
    signatures = {
        (
            round(item.volume, 3),
            tuple(sorted(round(value, 3) for value in item.dimensions)),
            item.face_count,
        )
        for item in summaries
    }
    return len(signatures)


def _detect_units(path: Path) -> str:
    if path.suffix.lower() not in {".step", ".stp"}:
        return "millimetres (normalized by OpenCascade)"
    text = path.read_text(encoding="latin-1", errors="ignore")
    if re.search(r"SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)", text):
        return "millimetres (declared by STEP SI unit)"
    return "millimetres (normalized by OpenCascade; STEP declaration not recognized)"


def _step_product_names(path: Path) -> tuple[str, ...]:
    if path.suffix.lower() not in {".step", ".stp"}:
        return ()
    text = path.read_text(encoding="latin-1", errors="ignore")
    names = re.findall(r"PRODUCT\s*\(\s*'((?:''|[^'])*)'", text)
    return tuple(dict.fromkeys(name.replace("''", "'") for name in names))


def format_report(
    analysis: CadAnalysis,
    *,
    nominal: tuple[float, float, float] | None = None,
) -> str:
    """Format a concise human-readable report and proposed JSON fragment."""

    length_taper = trapezoid_taper(analysis.top_length, analysis.bottom_length)
    width_taper = trapezoid_taper(analysis.top_width, analysis.bottom_width)
    lines = [
        "Hammond enclosure CAD analysis",
        "================================",
        f"CAD file successfully loaded: {analysis.source}",
        f"Backend: {analysis.backend}",
        f"CAD units: {analysis.units}",
        f"Solid instances found: {len(analysis.solids)}",
        f"Unique solid geometries: {analysis.unique_geometry_count}",
        f"STEP product names: {', '.join(analysis.product_names) or 'not available'}",
        f"Enclosure body: solid {analysis.body_index} (largest enclosure-like solid)",
        f"Removable lid: solid {analysis.lid_index} (matching thin planform)",
        "Remaining solids: assembly screws or other small hardware",
        "",
        "Coordinate interpretation",
        "-------------------------",
        f"Length axis: {analysis.length_axis}",
        f"Width axis: {analysis.width_axis}",
        f"Body-height axis: {analysis.height_axis}",
        (
            f"Face A: closed plane at {analysis.height_axis}="
            f"{analysis.closed_coordinate:.3f}"
        ),
        f"Open/lid plane: {analysis.height_axis}={analysis.open_coordinate:.3f}",
        f"Body height: {analysis.body_height:.3f} mm",
        f"Lid solid height: {analysis.lid_height:.3f} mm",
        f"Lid projection beyond open plane: {analysis.lid_projection:.3f} mm",
        "",
        "Measured sections",
        "-----------------",
        (
            f"Near Face A ({analysis.height_axis}="
            f"{analysis.near_closed.coordinate:.3f}): "
            f"{analysis.near_closed.length:.3f} x "
            f"{analysis.near_closed.width:.3f} mm"
        ),
        (
            f"Near open edge ({analysis.height_axis}="
            f"{analysis.near_open.coordinate:.3f}): "
            f"{analysis.near_open.length:.3f} x "
            f"{analysis.near_open.width:.3f} mm"
        ),
        "The dimensions below extrapolate the stable straight-wall sections to",
        "the physical body planes; exact boundary sections are distorted by",
        "fillets and lips.",
        "",
        "Drafted body dimensions",
        "-----------------------",
        f"Top length at Face A side: {analysis.top_length:.3f} mm",
        f"Bottom length at lid side: {analysis.bottom_length:.3f} mm",
        f"Top width at Face A side: {analysis.top_width:.3f} mm",
        f"Bottom width at lid side: {analysis.bottom_width:.3f} mm",
        f"Long-side difference: {length_taper.difference:.3f} mm",
        f"Long-side offset per side: {length_taper.side_offset:.3f} mm",
        f"Short-side difference: {width_taper.difference:.3f} mm",
        f"Short-side offset per side: {width_taper.side_offset:.3f} mm",
        f"Length-direction wall draft: {analysis.length_draft_degrees:.3f} degrees",
        f"Width-direction wall draft: {analysis.width_draft_degrees:.3f} degrees",
        f"Length fit R^2: {analysis.length_fit_r_squared:.9f}",
        f"Width fit R^2: {analysis.width_fit_r_squared:.9f}",
        f"Section-centre drift: {analysis.symmetry_deviation:.6f} mm",
        (
            f"Main outer plan corner radius: {analysis.corner_radius:.3f} mm"
            if analysis.corner_radius is not None
            else "Main outer plan corner radius: not reliably detected"
        ),
    ]
    if nominal is not None:
        overall_height = analysis.body_height + analysis.lid_projection
        lines.extend(
            [
                "",
                "Nominal plausibility check",
                "--------------------------",
                (
                    "Published nominal L x W x H: "
                    f"{nominal[0]:.0f} x {nominal[1]:.0f} x "
                    f"{nominal[2]:.0f} mm"
                ),
                (
                    "CAD overall body plan/open edge and assembled height: "
                    f"{analysis.bottom_length:.3f} x {analysis.bottom_width:.3f} x "
                    f"{overall_height:.3f} mm"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "Proposed JSON fragment (2 decimal places)",
            "-----------------------------------------",
            json.dumps(
                proposed_face_json(
                    top_length=analysis.top_length,
                    bottom_length=analysis.bottom_length,
                    top_width=analysis.top_width,
                    bottom_width=analysis.bottom_width,
                    body_height=analysis.body_height,
                ),
                indent=2,
            ),
        ]
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cad_file", type=Path)
    parser.add_argument(
        "--section-offset",
        type=float,
        default=1.2,
        help="distance in mm from each body boundary (default: 1.2)",
    )
    parser.add_argument(
        "--nominal",
        nargs=3,
        type=float,
        metavar=("LENGTH", "WIDTH", "HEIGHT"),
        help="optional published overall dimensions for comparison",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line CAD analysis."""

    arguments = _parser().parse_args(argv)
    try:
        analysis = analyze_cad(
            arguments.cad_file,
            section_offset=arguments.section_offset,
        )
    except (CadAnalysisError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    nominal = tuple(arguments.nominal) if arguments.nominal else None
    print(format_report(analysis, nominal=nominal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
