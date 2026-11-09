# `tracks.py` — Track elements and combining them

[← Back to index](../README.md)

**Depends on:** `track_helpers`, `section_checks`, `file_utils`, `physics.G`, numpy
**Used by:** `GUI.py`, `web_backend.py`, `recommendation.py` (through the builder map)

Holds `class TrackPart`, whose static methods build each track element and join elements into a
full coaster. Every builder returns the [12-array track format](../README.md#the-12-array-track-format)
(+ file name). Start builders also return the exit speed.

## Track element builders

| Function | Track type | Input | How it's made | Returns |
|---|---|---|---|---|
| `launcher_func(L)` | Launcher | length L | Flat straight; `v_exit = √(2·1.5g·L)` | `(arrays, v_exit)` |
| `lifthill_func(h)` | Lift Hill | height h | Prebuilt `cometlifthill.csv` scaled to h; `v_exit = √(2g·h_max)` | `(arrays, v_exit)` |
| `rollback_func(h)` | Rollback | height h | 60° slope + circular curve + flat station (equations) | `(arrays, v_exit)` |
| `loopCG_func(h)` | Loop | height h | Constant-g loop, simulated step by step, scaled to height h, side-offset exit | arrays |
| `camelback_func(h)` | Camelback | height h | Prebuilt `cometcamelback.csv`, X squashed to 1/3 | arrays |
| `corkscrew_func(h)` | Corkscrew | height h | Ramp in → 1.5 barrel rolls (radius h/2) → ramp out | arrays |
| `cobrarollCG_func(h)` | Cobra Roll | height h | Euler-spiral half loop + half corkscrew, then mirrored; reverses direction | arrays |
| `helix_func(h)` | Helix | height h | Climb, 1.5-turn clothoid spiral (radius 2h, banking 45°→63.4°), exit | arrays |
| `horseshoe_func(h)` | Horseshoe | height h | 180° turn that climbs to h, banking rolls in/out | arrays |
| `brake_func(L)` | Brake | length L | Flat straight (1.5g deceleration is applied in the checks) | arrays |
| `rollup_func(h)` | Rollup | height h | Circular curve into 60° incline (train rolls back) | arrays |
| `from_data(scale, name)` | — | — | Load any prebuilt CSV (not used by the apps) | arrays |
| `loopwith2Rs(r1, r2)` | — | — | TODO, returns `None` | — |

## Combining: `combine_tracks(*parts, section_folder, coaster_name, write=True, losses=None)`

Each `part` is `{"section", "type", "arrays", "v_exit"}`.

1. `section_checks.initialize_track_data(parts)` — blank stats/checks per section.
2. Speed leaving `Starts`: `section_checks.start_exit_speed(...)`.
3. For each later part:
   - `section_checks.analyze_section(...)` **before** moving it → stats, checks, exit speed (fed to the next part).
   - Sections in `INVERT_TRACKS` (`Thrills 2`, `Ends`) are flipped so the track heads back the other way (the Rollup is mirrored instead).
   - Shift the part so its first point sits on the previous part's last point.
4. Concatenate all parts.
5. `add_loop_back(...)` — unless the coaster starts with a Rollback or ends with a Rollup, adds a straight + semicircle + straight back to the station.
6. If `write`: `file_utils.csv_noLimits_format(...)` → `<section_folder>/Coasters/<coaster_name>_0.csv`.
7. `calculate_xy_composition(...)` — per-section side-profile (horizontal distance vs height).

**Returns** `(combined_track, xy_composition, track_data)`:
- `combined_track` — 12 arrays + `coaster_name`
- `xy_composition` — list of `{"section", "type", "XY", "Z"}`
- `track_data` — `{section: {"section_type", "stats", "checks"}}`

## Adding a new track type
1. Write `new_func(value)` here using helpers from `track_helpers.py` (`_build` / `_finish`).
2. Add it to `track_function_map` and the section lists in **both** `GUI.py` and `web_backend.py`.
3. If it needs physics checks, add it to the lists at the top of `section_checks.py`.
