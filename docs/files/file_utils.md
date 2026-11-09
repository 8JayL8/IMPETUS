# `file_utils.py` — Folders, CSV files and image export

[← Back to index](../README.md)

**Depends on:** numpy, matplotlib, csv, os/shutil, threading
**Used by:** `tracks.py`, `track_helpers.py`, `recommendation.py`, `GUI.py`, `web_backend.py`

Everything that touches the disk.

## Folders

| Function | Purpose |
|---|---|
| `get_section_path(section_folder)` | Absolute path of a section folder inside the `IMPETUS` folder |
| `build_exists(section_folder, coaster_name)` | `True` if `<section>/Coasters/<coaster>_0.csv` exists |
| `initalize_folders(section_folder, coaster_name)` | Clears only this coaster's old files, creates `Coasters/`, `Images/<coaster>/`, `Segments/<coaster>/`, sets the segments folder. Returns `{"master", "coaster", "images", "segments"}` |
| `set_segments_dir(path)` / `_get_segments_dir()` | Where `write_csv` saves elements. Stored **per thread** (`threading.local`) so web requests don't interfere |
| `no_segment_writes()` | Context manager: temporarily turns segment saving off (previews, recommendations) |
| `_remove(path)` | Delete a file/folder, printing instead of crashing on failure |

## CSV

| Function | Purpose |
|---|---|
| `read_csv(file_name)` | Read `Prebuilt_tracks/<file_name>` (comma or whitespace separated, header skipped). Cached once per file; returns a copy |
| `write_csv(data, pts, prop, elementname)` | Save one element to `<segments>/<elementname>_<prop>.csv`. Does nothing if no segments folder is set |
| `csv_noLimits_format(data, pts, prop, elementname)` | Save the whole coaster as a **tab-separated NoLimits 2 spline** (`No.`, `PosX` … `UpZ`, scientific notation). Re-test in NoLimits 2 after changing it |

> `read_csv` uses the relative path `Prebuilt_tracks/`, so run the apps from the repository folder.

## Image export (desktop GUI only)

| Function | Purpose |
|---|---|
| `export_layouts(images_folder, track_data, xy_composition, track_plots)` | Entry point: writes all SVGs including `combined_track_views.svg` |
| `calculate_segment_boundaries(xy_composition)` | Where each section starts/ends along the profile |
| `combined_view(...)` | Top view + section 1–2, 3, 4–5 side profiles on one figure |
| `export_individual_views(...)` | Each GUI plot saved on its own |
| `export_printed_pieces(...)` | Splits views into printable pieces with a Greek-key border |
| `_greek_key(...)`, `_copy_line(...)` | Drawing helpers |
