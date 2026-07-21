# Enclosure CAD analysis summary

Phase 1 analyzed every STEP or IGES file found directly under `tools/cad/`.
Filenames were normalized case-insensitively and matched only when the model
token corresponded exactly to one existing catalog model. All seven matches
were unambiguous. This analysis was completed before the reviewed READY values
were applied to the catalog in Phase 2.

| Model | Catalog identifier | Status | Top length | Bottom length | Top width | Bottom width | Body height | Draft L/W | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1550B | `hammond-1550b` | READY | 113.592 | 114.500 | 63.092 | 64.000 | 26.000 | 1.000° / 1.000° | Stable at 2–4 mm section offsets; default 1.2 mm intersects an edge detail. |
| 1590A | `hammond-1590a` | READY | 91.186 | 92.600 | 37.086 | 38.500 | 27.000 | 1.500° / 1.500° | Stable at 2–4 mm section offsets; default 1.2 mm intersects an edge detail. |
| 1590B | `hammond-1590b` | READY | 111.222 | 112.400 | 59.322 | 60.500 | 27.000 | 1.250° / 1.250° | Default 1.2 mm analysis passed. |
| 1590B2 | `hammond-1590b2` | READY | 110.938 | 112.400 | 59.038 | 60.500 | 33.500 | 1.250° / 1.250° | Default 1.2 mm analysis passed. |
| 1590BB | `hammond-1590bb` | READY — VERIFIED | 116.880 | 119.500 | 91.380 | 94.000 | 30.000 | 2.500° / 2.500° | STEP and IGES agree at 1.2, 2.0, 3.0, and 4.0 mm offsets. |
| 1590G | `hammond-1590g` | READY | 98.874 | 100.000 | 48.874 | 50.000 | 21.500 | 1.500° / 1.500° | Stable at 2–4 mm section offsets; default 1.2 mm intersects an edge detail. |
| 1590X | `hammond-1590x` | READY | 142.461 | 145.200 | 118.461 | 121.200 | 52.300 | 1.500° / 1.500° | Default 1.2 mm analysis passed. |

All dimensions are millimetres. Every READY result has length and width fit
R² = 1.000000000, zero measured section-centre drift, top dimensions no larger
than bottom dimensions, and an open-edge plan matching the current Face A
catalog dimensions. Each assembly contains six solid instances: body solid 0,
lid solid 1, and four screw instances represented by one repeated geometry.

The catalog side heights often describe assembled external height, while the
proposals deliberately use CAD enclosure-body height. Individual reports call
out each comparison.

The unusually large 1590BB draft received additional cross-format and
multi-offset verification. All eight STEP/IGES runs independently selected
body 0 and lid 1, passed both R² gates at 1.000000000, and returned identical
dimensions, 2.500° drafts, and zero centre drift at displayed precision.

Phase 2 subsequently converted B–E for all seven READY models to the proposed
two-decimal trapezoids. Face A remained unchanged. The existing verified
1590XX measurements were retained without modification.
