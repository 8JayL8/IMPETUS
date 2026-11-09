# `web_backend.py` — Web build logic (no Qt)

[← Back to index](../README.md)

**Depends on:** `tracks`, `file_utils`, `physics`, `section_checks`, `recommendation`
**Used by:** [`server.py`](server.md)

The same build loop as `GUI.start_generating()`, but with no Qt code, so the web server can use it.
It validates input from the browser, builds the coaster, and converts NumPy results into JSON.

## Constants

| Name | Purpose |
|---|---|
| `SECTIONS`, `STARTS`, `THRILLS`, `TURNS`, `ENDS`, `SECTION_TRACKS` | Allowed track types per section (**keep in sync with `GUI.py`**) |
| `RECOMMEND_SECTIONS` | All sections except `Starts` |
| `LENGTH_TRACKS` | `{"Launcher", "Brake"}` — value is a length; everything else is a height |
| `VALUE_RANGE` | `(1, 50)` slider range |
| `CHECK_WARNINGS` | Check key → message |
| `track_function_map` | Track type → `tracks.TrackPart.*_func` |
| `PHYSICS_DEFAULTS`, `_PHYSICS_LIMITS` | Default and allowed values for μ, Cd, frontal area, mass |
| `CHAIN_SPEED`, `CRAWL_SPEED` | Speeds (m/s) used only by the ride animation (lift chain; after brakes / return track) |
| `_export_lock` | Only one export writes files at a time |
| `_SAFE_NAME` | Regex for allowed folder / coaster names |

## Public functions (called by `server.py`)

| Function | What it does |
|---|---|
| `options()` | Everything the page needs to build its controls |
| `preview(raw_requests, raw_physics)` | Validate → build inside `file_utils.no_segment_writes()` → JSON. **Writes nothing.** |
| `export(raw_requests, section_folder, coaster_name, overwrite, raw_physics)` | Validate names → (under lock) check for an existing build → `initalize_folders` → build with `write=True` → JSON + `saved_to` |
| `recommendations(start_type, start_value, raw_physics, raw_tracks)` | Calls `EnergyRecommendation.get_recommendations`; with losses on, passes the user's current picks so each section uses its real entry speed |

## Internal helpers

| Function | What it does |
|---|---|
| `validate_requests(raw)` | Checks section / type / value; `Starts` required; returns ordered `(section, type, value)` tuples. Raises `BuildError`. |
| `parse_losses(raw)` | Friction / air settings from the page → `physics.make_losses(...)` or `None` |
| `_build(...)` | Calls each builder, then `tracks.TrackPart.combine_tracks`; also computes ride speeds |
| `_start_speeds(part, losses)` | Speed along the `Starts` element (launch acceleration, chain lift, or drop) |
| `_ride_speeds(...)` | Speed at every point of the whole track for the ride animation; `NaN` after a stall |
| `_to_json(...)` | Packs track arrays (`X Y Z Nx Ny Nz V`), per-section stats/checks/warnings, and the side profile |
| `_num`, `_arr` | NumPy → JSON-safe numbers / rounded lists (NaN/inf → `null`/0) |

## `BuildError`
A `ValueError` subclass for user mistakes. `server.py` turns it into HTTP 400 and the message is shown as-is.

## Response shape of `preview` / `export`
```jsonc
{
  "track":   { "X": [...], "Y": [...], "Z": [...], "Nx": [...], "Ny": [...], "Nz": [...], "V": [...] },
  "losses":  null | { "mu": 0.015, "k_air": 0.0004 },
  "sections": [ { "section", "type", "value", "points", "stats", "checks", "warnings", "passed" } ],
  "profile": [ { "section", "type", "XY": [...], "Z": [...] } ],
  "saved_to": { "coaster_csv", "segments" }      // export only
}
```

## Thread safety
`file_utils` keeps the segments folder **per thread**, so previews and recommendations can run in
parallel. Exports also take `_export_lock` so two users cannot claim the same new name at once.
