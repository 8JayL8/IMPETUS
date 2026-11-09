# `track_helpers.py` — Shared maths for track builders

[← Back to index](../README.md)

**Depends on:** `file_utils`, numpy
**Used by:** `tracks.py` only

Private helpers (names start with `_`) used by the `TrackPart` builders: direction/normal vectors,
smooth ramps, shape pieces, and saving/loading track parts.

## Vectors and normals

| Function | Purpose |
|---|---|
| `_front(X, Y, Z)` | Front (tangent) vectors = step to the next point |
| `_left(X, Y, Z, Fx, Fy, Fz)` | Left vectors (cross product) |
| `_stretch_front(Fx, Fy, Fz, x_stretch)` | Re-normalise front vectors after a prebuilt track is stretched in X |
| `_planar_normals(X, Y)` | Up-vectors for a track that stays in the X–Y plane (rollback, rollup) |
| `_rotate_normals(X, Y, Z, Phi, ...)` | Roll the up-vectors by angle `Phi` around the direction of travel |
| `_banked_normals(X, Y, Z, Phi)` | Up-vectors for a banked turn |
| `_carry_normal(P, T, N0)` | Carry an up-vector along a path without twisting (parallel transport) |
| `_rotate_about(v, axis, angle)` | Rotate vectors about an axis (Rodrigues) |
| `_integrate_directions(T, ds)` | Positions from tangent directions and step length |

## Shapes and ramps

| Function | Purpose |
|---|---|
| `_smootherstep(s)` | Smooth 0→1 curve with zero slope and curvature at both ends |
| `_smooth_ramp(y_end, slope_end, length, pts)` | Ramp from flat ground to a given height and slope |
| `_min_radius_xy(X, Y)` | Tightest radius of a 2D curve |
| `_gentle_ramp(y_end, slope_end, target_radius)` | Ramp whose tightest radius is about `target_radius` (corkscrew lead-in) |
| `_cobra_unit_shape(neck_fraction, n_fine)` | Cobra roll half-shape at top radius 1 (cached with `lru_cache`, then scaled) |

## Building / saving a part

| Function | Purpose |
|---|---|
| `_finish(file_name, prop, X…Nz)` | Write the segment CSV via `file_utils.write_csv`, return the 13-tuple |
| `_build(file_name, prop, X, Y, Z, Nx, Ny, Nz)` | Same, but works out Front and Left vectors first |
| `_load_prebuilt(csv_name, h, x_stretch, file_name)` | Read `Prebuilt_tracks/<csv_name>`, scale so max height = h, stretch X, save segment |

`write_csv` only writes if a segments folder is set (during an export / GUI build); otherwise it does nothing.
