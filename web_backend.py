# web_backend.py
# Track building for the web frontend (server.py + web/).
# This is the same build loop as GUI.py's start_generating(), without any Qt code,
# so the PyQt GUI and the web frontend can both be used.
#
# When adding new track types, add them here AND in GUI.py.
import math
import re
import threading

import numpy as np

import tracks
import file_utils
import physics
import section_checks
from recommendation import EnergyRecommendation

# ========================================================================
SECTIONS = ["Starts", "Thrills 1", "Turns", "Thrills 2", "Ends"]
STARTS = ["Launcher", "Lift Hill", "Rollback"]
THRILLS = ["Loop", "Camelback", "Corkscrew"]
TURNS = ["Cobra Roll", "Horseshoe", "Helix"]
ENDS = ["Brake", "Rollup"]
SECTION_TRACKS = {
    "Starts": STARTS,
    "Thrills 1": THRILLS,
    "Turns": TURNS,
    "Thrills 2": THRILLS,
    "Ends": ENDS,
}
RECOMMEND_SECTIONS = {name: types for name, types in SECTION_TRACKS.items() if name != "Starts"}
LENGTH_TRACKS = {"Launcher", "Brake"}   # every other track is controlled by its height
VALUE_RANGE = (1, 50)                   # same slider range as the GUI

CHECK_WARNINGS = {
    "velocity_check": "Not enough velocity to get through this section.",
    "valley_check": "Valley G-force exceeds 5Gs.",
    "inversion_check": "Too slow or too fast to clear the inversion peak.",
    "peak_check": "Speed too high over crest (Airborne).",
    "lateral_check": "Lateral turning G-forces exceed safe rider comfort (>1.5G).",
    "rollup_check": "Rollup incline is not tall enough. The coaster will fly off the track.",
    "brake_check": "Entry speed into exceeds allowed stopping threshold.",
}

track_function_map = {
    "Launcher": tracks.TrackPart.launcher_func,
    "Lift Hill": tracks.TrackPart.lifthill_func,
    "Rollback": tracks.TrackPart.rollback_func,
    "Loop": tracks.TrackPart.loopCG_func,
    "Camelback": tracks.TrackPart.camelback_func,
    "Corkscrew": tracks.TrackPart.corkscrew_func,
    "Cobra Roll": tracks.TrackPart.cobrarollCG_func,
    "Horseshoe": tracks.TrackPart.horseshoe_func,
    "Helix": tracks.TrackPart.helix_func,
    "Brake": tracks.TrackPart.brake_func,
    "Rollup": tracks.TrackPart.rollup_func,
}

# file_utils keeps the segments folder in a global, so only one build may run at a time
_build_lock = threading.Lock()
_SAFE_NAME = re.compile(r"^[A-Za-z0-9 _\-]{1,64}$")
# ========================================================================


class BuildError(ValueError):
    """Bad input from the frontend (shown to the user as-is)."""


def options():
    return {
        "sections": SECTIONS,
        "section_tracks": SECTION_TRACKS,
        "length_tracks": sorted(LENGTH_TRACKS),
        "value_range": VALUE_RANGE,
        "check_warnings": CHECK_WARNINGS,
        "physics_defaults": PHYSICS_DEFAULTS,
        "physics_limits": _PHYSICS_LIMITS,
    }


# Checks the frontend's list of {section, type, value} and returns (section, type, value) tuples.
# 'Starts' is required; any other section can be left out (None type).
def validate_requests(raw):
    by_section = {}
    for item in raw:
        section, track_type = item.get("section"), item.get("type")
        if not track_type:
            continue
        if section not in SECTION_TRACKS:
            raise BuildError(f"Unknown section {section!r}.")
        if track_type not in SECTION_TRACKS[section]:
            raise BuildError(f"{track_type} can't be used in {section}.")
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            raise BuildError(f"Enter a number for the {track_type} track.")
        low, high = VALUE_RANGE
        if not (low <= value <= high):
            raise BuildError(f"The {track_type} track value must be within {low} - {high}.")
        by_section[section] = (section, track_type, value)

    if "Starts" not in by_section:
        raise BuildError("Pick a track type for 'Starts'.")
    return [by_section[s] for s in SECTIONS if s in by_section]


# ========================================================================
#                   Friction / air resistance settings
# ========================================================================
# Defaults used when the user first turns them on in the web page
PHYSICS_DEFAULTS = {
    "friction": {"mu": 0.015},                                  # rolling-friction coefficient
    "air": {"cd": 0.9, "area": 2.0, "mass": 5000.0},            # drag coefficient, frontal area m^2, train mass kg
}
_PHYSICS_LIMITS = {"mu": (0.0, 0.2), "cd": (0.0, 3.0), "area": (0.1, 20.0), "mass": (100.0, 50000.0)}


# {"friction": {"enabled": bool, "mu": ..}, "air": {"enabled": bool, "cd": .., "area": .., "mass": ..}}
# -> physics.make_losses(...) dict, or None when both are off
def parse_losses(raw):
    if not raw:
        return None
    friction, air = raw.get("friction") or {}, raw.get("air") or {}

    def value(group, key):
        default = PHYSICS_DEFAULTS["friction" if key == "mu" else "air"][key]
        try:
            v = float(group.get(key, default))
        except (TypeError, ValueError):
            raise BuildError(f"Enter a number for {key}.")
        low, high = _PHYSICS_LIMITS[key]
        if not (low <= v <= high):
            raise BuildError(f"{key} must be within {low:g} - {high:g}.")
        return v

    mu = value(friction, "mu") if friction.get("enabled") else 0.0
    if air.get("enabled"):
        return physics.make_losses(mu, value(air, "cd"), value(air, "area"), value(air, "mass"))
    return physics.make_losses(mu)


# Same loop as GUI.start_generating() steps 4-5
def _build(requests, section_folder=None, coaster_name="preview", write=False, losses=None):
    data = []
    for section, track_type, value in requests:
        result = track_function_map[track_type](value)
        segment_v_exit = 0.0
        if track_type in STARTS and isinstance(result, tuple) and len(result) == 2:
            segment, raw_v = result
            segment_v_exit = float(np.ravel(raw_v)[0])
        else:
            segment = result
        data.append({"section": section, "type": track_type, "arrays": segment, "v_exit": segment_v_exit})

    combined, xy_composition, track_data = tracks.TrackPart.combine_tracks(
        *data, section_folder=section_folder, coaster_name=coaster_name, write=write, losses=losses)
    part_lengths = [int(np.ravel(part["arrays"][0]).size) for part in data]
    speeds = _ride_speeds(data, track_data, combined, losses)
    return combined, xy_composition, track_data, part_lengths, speeds


# ===== Speed at every point of the combined track, for the train ride in the web page =====
# Uses the same speeds as the physics checks (so the train stalls exactly where a check says it does),
# plus what the checks don't cover: the chain up the lift hill, the launch, and the slow roll back
# into the station.
CHAIN_SPEED = 3.0    # m/s up the lift hill
CRAWL_SPEED = 2.5    # m/s after the brakes / on the return track


def _start_speeds(part, losses):
    X, Y, Z = (np.ravel(a).astype(float) for a in part["arrays"][:3])
    n = len(X)
    if part["type"] == "Launcher":
        s = np.r_[0, np.cumsum(np.sqrt(np.diff(X)**2 + np.diff(Y)**2 + np.diff(Z)**2))]
        return np.sqrt(0.25 + 2 * 1.5 * physics.G * s)
    start = int(np.argmax(Y)) if part["type"] == "Lift Hill" else 0
    v = np.full(n, CHAIN_SPEED)
    geometry = physics.track_geometry((X[start:], Y[start:], Z[start:]))
    drop = physics.calculate_velocity(0.1, Y[start:], geometry, losses)
    if part["type"] == "Lift Hill":
        # the chain lets go at its own speed, so never slower than that over the crest
        # (the checks start the drop from rest, which is slightly slower: the safe side)
        drop = np.where(np.isnan(drop), np.nan, np.maximum(drop, CHAIN_SPEED))
    v[start:] = drop
    return v


def _ride_speeds(data, track_data, combined, losses):
    pieces = [_start_speeds(data[0], losses)]
    for part in data[1:]:
        v = np.array(track_data[part["section"]]["stats"]["velocities"], dtype=float)
        if part["type"] == "Brake":
            v = np.where(np.isnan(v) | (v < CRAWL_SPEED), CRAWL_SPEED, v)   # brakes hold a slow crawl
        pieces.append(v)
    v = np.concatenate(pieces)
    # once the train has stalled it stays stopped
    stalled = np.where(np.isnan(v))[0]
    if len(stalled):
        v[stalled[0]:] = np.nan
    total = len(np.ravel(combined[0]))
    if total > len(v):
        rest = np.full(total - len(v), np.nan if len(stalled) else CRAWL_SPEED)
        v = np.concatenate([v, rest])
    return v


# Live preview: nothing is written to disk
def preview(raw_requests, raw_physics=None):
    requests = validate_requests(raw_requests)
    losses = parse_losses(raw_physics)
    with _build_lock, file_utils.no_segment_writes():
        built = _build(requests, losses=losses)
    return _to_json(requests, *built, losses)


# Export: writes <section>/Coasters/<coaster>_0.csv and <section>/Segments/<coaster>/*.csv
# (the matplotlib images are only made by the PyQt GUI)
def export(raw_requests, section_folder, coaster_name, overwrite=False, raw_physics=None):
    requests = validate_requests(raw_requests)
    losses = parse_losses(raw_physics)
    section_folder = (section_folder or "").strip() or "Test_Section"
    coaster_name = (coaster_name or "").strip() or "Test_Coaster"
    for label, name in (("Section", section_folder), ("Coaster", coaster_name)):
        if not _SAFE_NAME.match(name):
            raise BuildError(f"{label} name may only use letters, numbers, spaces, '_' and '-'.")

    if file_utils.build_exists(section_folder, coaster_name) and not overwrite:
        return {"exists": True, "section_folder": section_folder, "coaster_name": coaster_name}

    with _build_lock:
        folders = file_utils.initalize_folders(section_folder, coaster_name)
        try:
            built = _build(requests, folders["master"], coaster_name, write=True, losses=losses)
        finally:
            file_utils._segments_dir = None   # later previews must never write segments

    result = _to_json(requests, *built, losses)
    result["saved_to"] = {
        "coaster_csv": f"{folders['coaster']}\\{coaster_name}_0.csv",
        "segments": folders["segments"],
    }
    return result


# raw_tracks: the current picks ({section, type, value} list, same as preview). With friction / air
# resistance on, they set the speed entering each section; frictionless they aren't needed.
def recommendations(start_type, start_value, raw_physics=None, raw_tracks=None):
    if start_type not in STARTS:
        raise BuildError(f"{start_type!r} is not a start track.")
    losses = parse_losses(raw_physics)
    chosen = {}
    if losses and raw_tracks:
        for item in raw_tracks:
            section, track_type = item.get("section"), item.get("type")
            if section in RECOMMEND_SECTIONS and track_type in SECTION_TRACKS[section]:
                try:
                    chosen[section] = (track_type, float(item.get("value")))
                except (TypeError, ValueError):
                    pass   # still typing: treat the section as skipped
    with _build_lock:
        recs = EnergyRecommendation.get_recommendations(
            start_type, float(start_value), track_function_map, RECOMMEND_SECTIONS, value_range=VALUE_RANGE,
            losses=losses, chosen=chosen)
    return {
        "v_exit": _num(recs["v_exit"]),
        "v_entry": {s: _num(v) for s, v in recs["v_entry"].items()},
        "sections": {s: {t: (list(b) if b else None) for t, b in recs[s].items()} for s in RECOMMEND_SECTIONS},
    }


# ========================================================================
#                       numpy -> JSON helpers
# ========================================================================
def _num(value):
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    value = float(value)
    return value if math.isfinite(value) else None


def _arr(values, decimals=3):
    values = np.nan_to_num(np.ravel(values).astype(float), nan=0.0, posinf=0.0, neginf=0.0)
    return np.round(values, decimals).tolist()


def _to_json(requests, combined, xy_composition, track_data, part_lengths, speeds, losses=None):
    X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz, _name = combined

    sections = []
    for (section, track_type, value), length in zip(requests, part_lengths):
        info = track_data[section]
        checks = {k: (None if v is None else bool(v)) for k, v in info["checks"].items()}
        # Starts sections aren't checked (same as the GUI)
        failed = [] if section == "Starts" else [CHECK_WARNINGS[k] for k, v in checks.items() if v is False]
        # Only single numbers are sent; the per-point arrays (velocities, radius) are skipped
        stats = {k: _num(v) for k, v in info["stats"].items() if v is None or np.ndim(v) == 0}
        sections.append({
            "section": section, "type": track_type, "value": value, "points": length,
            "stats": stats, "checks": checks, "warnings": failed, "passed": not failed,
        })

    return {
        "track": {"X": _arr(X), "Y": _arr(Y), "Z": _arr(Z), "Nx": _arr(Nx, 4), "Ny": _arr(Ny, 4), "Nz": _arr(Nz, 4),
                  # ride speed at every point (m/s); null where the train has stopped
                  "V": [None if not math.isfinite(v) else round(float(v), 3) for v in speeds]},
        "losses": losses,
        "sections": sections,
        "profile": [{"section": seg["section"], "type": seg["type"], "XY": _arr(seg["XY"]), "Z": _arr(seg["Z"])}
                    for seg in xy_composition],
    }
