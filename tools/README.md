# CAD analysis tooling

The CAD analyzer is intentionally separate from pedal-drill's runtime package.
It requires CadQuery and OpenCascade only when inspecting an enclosure model.

```console
python3.12 -m venv .venv-cad
. .venv-cad/bin/activate
python -m pip install -r tools/requirements-cad.txt
python tools/analyze_enclosure_cad.py path/to/1590XX.stp --nominal 145 121 39
```

STEP is the preferred input. IGES is supported as a fallback by OpenCascade.
The backend does not import Parasolid (`.x_t`) directly; use the corresponding
STEP or IGES file instead.

The tool identifies the largest enclosure-like solid as the body and requires
one matching, shallow planform solid as the removable lid. It rejects files
where those roles are ambiguous. Dimensions are obtained from planar sections
through the body rather than from the assembly bounding box alone.
