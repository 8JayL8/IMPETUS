# `physics.py` — Formulas and pass/fail checks

[← Back to index](../README.md)

**Depends on:** numpy only
**Used by:** `section_checks.py`, `web_backend.py`, `tracks.py` (for `G`)

Pure maths, no track-type knowledge. Units are SI (m, m/s, kg); g-forces are in multiples of g.

## Constants

| Name | Value | Meaning |
|---|---|---|
| `G` | 9.8 | gravity (m/s²) |
| `BRAKE_DECEL_G` | 1.5 | brake deceleration (g) |
| `AIR_DENSITY` | 1.225 | kg/m³ at sea level |

## Speed and energy losses

| Function | Purpose |
|---|---|
| `make_losses(mu, drag_coefficient, frontal_area, mass)` | → `{"mu", "k_air"}` with `k_air = ½·ρ·Cd·A / m`, or `None` if both are zero |
| `calculate_velocity(v_entry, Y, geometry, losses, decel)` | Speed at every point. Frictionless: `v² = v₀² − 2g·Δy`. With losses/brakes: stepped along the track, losing `2·(μ·wheel force + k_air·v² + decel)·ds` each step. `NaN` once the train stalls |

## Geometry and forces

| Function | Purpose |
|---|---|
| `track_geometry(xyz, normals, window=2.0)` | Arc length `s`, unit tangent `T`, curvature vector, radius (measured over ~2 m), rider up/side directions `N` |
| `rider_forces(geometry, velocities)` | Seat (vertical) g and lateral g at every point |
| `calculate_R(xyz, forward)` | Older radius estimate from front-vector angle change (not currently called) |
| `find_valley(xyz, velocities, ...)` | Worst upward-curving dip in the lowest 25 % of the section → `(index, radius, n_y)` or `None` |

## Checks — each returns `(passed, value)`

| Function | Rule |
|---|---|
| `velocity_check(v)` | No `NaN` (train never stalls) |
| `valley_check(v, r, n_y)` | `(g·n_y + v²/r) / g < 5` |
| `inversion_check(v_top, r_top)` | At the top: `v²/(g·r) − 1 ≤ 3 g` and `v ≥ √(g·r)` |
| `inversion_seat_check(seat_g, N_y)` | Seat force ≥ 0 g everywhere the rider is upside down |
| `peak_check(v, r)` | Older single-point crest check (not currently called; `airtime_check` replaced it) |
| `airtime_check(seat_g)` | Seat force ≥ 0 g on the whole crest |
| `lateral_section_check(lateral_g)` | `abs(lateral) ≤ 1.5 g` everywhere → also returns the worst index |
| `lateral_check(v, r, θ)` | Older single-point banked-turn formula (not currently called; `lateral_section_check` replaced it) |
| `rollup_check(v_bot, h)` | Climb height `v²/2g` must be less than the rollup height (train mustn't fly off the top) |
| `brake_check(v_bot, L)` | `v_bot ≤ √(2·1.5g·L)` (brake is long enough to stop the train) |
