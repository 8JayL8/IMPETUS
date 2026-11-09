# `server.py` — Web server (FastAPI)

[← Back to index](../README.md)

**Run:**
```powershell
python server.py                 # this computer only → http://127.0.0.1:8000
python server.py --lan           # also other devices on the network (address printed at startup)
python server.py --port 9000 --workers 2
```
**Depends on:** `web_backend`, FastAPI, Pydantic, Uvicorn
**Used by:** the browser (`web/js/`)

A thin HTTP layer. It does no track maths itself: each route converts the request body to plain
dicts, calls a function in [`web_backend.py`](web_backend.md), and returns its JSON.
It also serves the static files in `web/`.

## Routes

| Method & path | Body model | Calls | Returns |
|---|---|---|---|
| `GET /api/options` | — | `web_backend.options()` | Sections, allowed types, slider range, warning texts, physics defaults/limits |
| `POST /api/preview` | `PreviewBody` | `web_backend.preview` | Built track (nothing saved to disk) |
| `POST /api/export` | `ExportBody` | `web_backend.export` | Same as preview + `saved_to` paths, or `{"exists": true}` if the name is taken and `overwrite` is false |
| `POST /api/recommendations` | `RecommendBody` | `web_backend.recommendations` | Safe value range per section / track type |
| `GET /` and static files | — | — | `web/index.html`, `style.css`, `js/*.js` |

## Request models (Pydantic)

| Model | Fields |
|---|---|
| `TrackRequest` | `section`, `type` (optional), `value` (optional) |
| `PhysicsBody` | `friction: {enabled, mu}`, `air: {enabled, cd, area, mass}` (both optional) |
| `PreviewBody` | `tracks: list[TrackRequest]`, `physics` |
| `ExportBody` | PreviewBody + `section_folder`, `coaster_name`, `overwrite` |
| `RecommendBody` | `start_type`, `start_value`, `physics`, `tracks` (current picks) |

## Error handling — `_run(fn, ...)`
- `web_backend.BuildError` (bad user input) → **HTTP 400** with the message.
- Any other exception (a track function failed for these values) → **HTTP 422** "Could not build this track".

The front end shows `detail` from the error response in the status bar.

## Other helpers
- `_physics(body)` — Pydantic model → dict (or `None`).
- `_lan_ip()` — finds this machine's LAN address to print at startup (no data is sent).
- `--lan` binds to `0.0.0.0` and defaults to up to 4 worker processes. There is no login, so only use it on a trusted network.
