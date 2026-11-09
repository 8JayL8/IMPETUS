# `GUI.py` — Desktop app (PyQt6)

[← Back to index](../README.md)

**Run:** `python GUI.py`
**Depends on:** `tracks`, `file_utils`, `recommendation` (plus PyQt6, matplotlib, numpy)
**Used by:** nothing — this is an entry point.

The original front end. A window with an **assembly panel** (one card per section with a dropdown,
slider and text box) and a **visual panel** (3D view, side profile, top view, drawn with matplotlib).
Pressing **Create** builds the coaster, runs the physics checks, colours each card green/red, and
writes the NoLimits 2 CSV plus SVG print layouts.

## Module-level constants

| Name | Purpose |
|---|---|
| `SECTIONS`, `STARTS`, `THRILLS`, `TURNS`, `ENDS`, `ALL_TRACKS` | Section names and the track types allowed in each |
| `RECOMMEND_SECTIONS` | Sections that get a recommended range (everything except `Starts`) |
| `CONTROL` | Which types are controlled by **Height** vs **Length** (Launcher, Brake) — sets the input label |
| `CHECK_WARNINGS` | Physics-check key → message shown when it fails |
| `track_function_map` | Track type name → `tracks.TrackPart.*_func` builder |
| `*_STYLE`, `REC_*_COLOR` | Qt stylesheet strings |

> ⚠️ `SECTIONS`, the type lists, `CHECK_WARNINGS` and `track_function_map` are duplicated in
> [`web_backend.py`](web_backend.md). Keep them in sync.

## Classes

| Class | What it does |
|---|---|
| `StatsDialog(QDialog)` | Pop-up table of a section's stats (speeds, radii, g-forces, banking) |
| `DualInputDialog(QDialog)` | Asks for the section folder and coaster name before saving |
| `RangeIndicatorSlider(QSlider)` | Slider that paints the recommended safe range as a green band (`set_recommendation_bounds`) |
| `MainWindow(QMainWindow)` | The whole app (below) |

## `MainWindow` methods

| Method | Role |
|---|---|
| `assembly_panel()` / `visual_panel()` | Build the left (inputs) and right (plots) panels |
| `single_page_view()` / `tabbed_view()` / `switch_view_mode()` | Two layouts for the section cards |
| `track_type(section)` | Builds the card UI for one section (dropdown + slider + text box + recommendation label) |
| `create_button()` | The **Create** button → `start_generating` |
| `update_recommendations()` | Calls `EnergyRecommendation.get_recommendations` whenever `Starts` changes; updates slider bands/labels |
| `start_generating()` | **Main pipeline** — see below |
| `process_physics_checks(checks)` | Turns failed checks into warning text and colours cards red/green |
| `update_visual(images_folder, track_data, xy_composition)` | Redraws matplotlib plots, then calls `file_utils.export_layouts` for SVGs |
| `show_section_stats(section)` | Opens a `StatsDialog` |
| `ask_build_names()` | Shows `DualInputDialog`, confirms overwrite via `file_utils.build_exists` |

## `start_generating()` step by step

1. Read every card; reject empty, non-numeric, out-of-range or unknown entries.
2. Ask for section folder + coaster name.
3. `file_utils.initalize_folders(...)` — creates the folders and tells `file_utils` where segment CSVs go.
4. Call `track_function_map[type](value)` for each section. Start builders return `(arrays, v_exit)`.
5. `tracks.TrackPart.combine_tracks(...)` — joins, checks physics, writes the coaster CSV.
6. `process_physics_checks` → warning dialog if anything failed; `update_visual` → plots + SVGs.

## Differences from the web app
- Frictionless only (no friction / air resistance toggles).
- Produces SVG print layouts (`Images/<coaster>/`); the web app does not.
- No ride simulation.
