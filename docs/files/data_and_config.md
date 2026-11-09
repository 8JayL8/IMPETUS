# Data and configuration files

[← Back to index](../README.md)

## `Prebuilt_tracks/`
Real or hand-made track shapes used as templates. Read by `file_utils.read_csv` (through
`track_helpers._load_prebuilt`), scaled to the height the user picks.

| File | Used by | Notes |
|---|---|---|
| `cometlifthill.csv` | `TrackPart.lifthill_func` | Lift Hill shape |
| `cometcamelback.csv` | `TrackPart.camelback_func` | Camelback shape (X squashed to 1/3) |
| `flashbackcobraroll.csv` | — | Old cobra roll; replaced by the equation-based `cobrarollCG_func` |
| `New_C.csv`, `New_Cobra_Maybe.csv`, `new_cobra.csv` | — | Experimental shapes, not used by the apps |

Format: a header row, then `No., PosX, PosY, PosZ, FrontX, FrontY, FrontZ, LeftX, LeftY, LeftZ, UpX, UpY, UpZ`
(comma- or whitespace-separated). Y is up.

## `requirements.txt`
| Package | Needed for |
|---|---|
| `PyQt6` | `GUI.py` |
| `matplotlib` | `GUI.py` plots, `file_utils` SVG export |
| `numpy` | everything |
| `fastapi`, `uvicorn` | `server.py` (web app) |

Install with `pip install -r requirements.txt`.

## `.gitignore`
Ignores `__pycache__/` and `*.pyc`. Generated section folders (e.g. `Test_Section/`) are **not**
ignored, so be careful not to commit exports by accident.

## Generated output
See [Output folders](../README.md#output-folders).
