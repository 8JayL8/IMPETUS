# `section_checks.py` — Which checks apply where

[← Back to index](../README.md)

**Depends on:** `physics`, numpy
**Used by:** `tracks.py` (`combine_tracks`), `recommendation.py`, `web_backend.py`

Decides **which** physics checks each track type gets and **where on the track** (top, worst valley,
worst lateral point …) the numbers come from. The formulas themselves are in [`physics.py`](physics.md).

## Check lists

| List | Track types |
|---|---|
| `VALLEY_CHECKS` | Loop, Camelback, Corkscrew, Cobra Roll |
| `INVERSION_CHECKS` | Loop, Corkscrew, Cobra Roll |
| `PEAK_CHECKS` | Camelback |
| `LATERAL_CHECKS` | Horseshoe, Helix |
| (special cases) | Rollup → `rollup_check`, Brake → `brake_check` |

Every section also gets `velocity_check` (the train must make it through).

## Functions

| Function | Purpose |
|---|---|
| `empty_section_data(section_type)` | Blank `{"section_type", "stats", "checks"}`. Checks start as `None` = "doesn't apply"; `velocity_check` starts `False` |
| `initialize_track_data(parts)` | `empty_section_data` for every section |
| `start_exit_speed(type, arrays, v_exit, losses)` | Speed leaving `Starts`. With losses, re-computes the drop of a Lift Hill / Rollback; Launcher unchanged |
| `analyze_section(section_name, type, arrays, v_entry, losses)` | **Main function** → `(stats, checks, v_exit)` |

## `analyze_section` in order
1. `physics.track_geometry` → curvature radius, tangent, normals.
2. `physics.calculate_velocity` → speed at every point (brakes add 1.5 g deceleration).
3. `velocity_check` — in `Ends` stopping is allowed; it only fails if the train never arrives. Elsewhere a stall → exit speed 0.
4. `physics.rider_forces` → seat (vertical) and lateral g at every point.
5. Valley: `physics.find_valley` + `valley_check` (< 5 g).
6. Inversion: `inversion_check` at the top + `inversion_seat_check` everywhere upside-down.
7. Peak: `airtime_check` (no negative g on a crest).
8. Lateral: `lateral_section_check` (< 1.5 g); Helix also records banking at top/bottom.
9. Rollup: `rollup_check`; Brake: `brake_check`.

A check value of `True` = pass, `False` = fail, `None` = not applicable. Front ends only warn on `False`.

## Stats keys
`acceleration`, `velocity_exit`, `velocities` (array), `v_top`, `v_bottom`, `radius` (array), `r_top`,
`r_bottom`, `deg_banking`, `deg_top`, `deg_bottom`, `g_top`, `g_min`, `g_valley`, `valley_ny`,
`g_lateral`, `v_lateral`, `r_lateral`.
