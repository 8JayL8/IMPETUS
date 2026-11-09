# `recommendation.py` — Safe slider ranges

[← Back to index](../README.md)

**Depends on:** `section_checks`, `file_utils`, numpy
**Used by:** `GUI.py` (`update_recommendations`), `web_backend.py` (`recommendations`)

`class EnergyRecommendation` answers: *"Given this start, which sizes of each track type pass every physics check?"*
It builds the element at every slider value (1–50) and runs the **same** `section_checks.analyze_section`
the Create/preview uses, so the recommendation always agrees with the final result.

## `get_recommendations(start_type, start_value, builders, sections, value_range=(1, 50), losses=None, chosen=None)`

| Argument | Meaning |
|---|---|
| `start_type`, `start_value` | The user's `Starts` pick |
| `builders` | `track_function_map` (track type → builder) |
| `sections` | `{section: [track types]}` to recommend for, in ride order |
| `losses` | `None` or `physics.make_losses(...)` |
| `chosen` | `{section: (type, value)}` already picked — only used with losses |

**Returns** `{"v_exit": float, "v_entry": {section: float}, <section>: {<type>: (min, max) or None}}`

### How entry speed is chosen
- **Frictionless:** every section uses the speed leaving `Starts` (no energy lost, elements start and end at about the same height).
- **With losses:** each section uses the speed it actually enters with, found by running the user's earlier picks (`_exit_speed`).

## Internals

| Name | Purpose |
|---|---|
| `_safe_range(build, section, type, v_entry, value_range, losses)` | Tests every integer value; returns the **longest continuous run** that passes, or `None` |
| `_exit_speed(builders, section, pick, v_entry, losses)` | Speed after the user's chosen element (0 if it stalls) |
| `_cache` | Results keyed by (is-Ends, type, entry speed, range, losses), up to 5000 entries; `Thrills 1` and `Thrills 2` share results |

All test builds run inside `file_utils.no_segment_writes()` so no files are written.
