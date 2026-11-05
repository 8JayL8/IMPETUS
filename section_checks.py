import numpy as np
import physics


# All the per-track-type rules: which checks each track type gets, and where on the
# track (top, valley, banking angle, ...) the values for those checks are taken from.
# The formulas themselves live in physics.py.


# List of all the checks for each track type
# ========================================================================
VALLEY_CHECKS = ["Loop", "Camelback", "Corkscrew", "Cobra Roll"]
INVERSION_CHECKS = ["Loop", "Corkscrew", "Cobra Roll"]
PEAK_CHECKS = ["Camelback"]
LATERAL_CHECKS = ["Horseshoe", "Helix"]
# ========================================================================


# Blank stats/checks for one section (what the GUI shows before anything is calculated)
def empty_section_data(section_type):
    stats = {
        "acceleration": None,
        "velocity_exit": None, "velocities": None, "v_top": None, "v_bottom": None,
        "radius": None, "r_top": None, "r_bottom": None,
        "deg_banking": None, "deg_top": None, "deg_bottom": None
    }

    # Launcher and Brake sections have a fixed acceleration
    if section_type == "Launcher":
        stats["acceleration"] = 1.5
    if section_type == "Brake":
        stats["acceleration"] = -1.5

    checks = {
        "velocity_check": False,
        "valley_check": None,
        "inversion_check": None,
        "peak_check": None,
        "lateral_check": None,
        "rollup_check": None,
        "brake_check": None
    }

    return {"section_type": section_type, "stats": stats, "checks": checks}


# Blank data for every section of the coaster
def initialize_track_data(parts):
    return {part["section"]: empty_section_data(part["type"]) for part in parts}


# Bank angle = angle between the track normal and vertical (Y is up)
def _bank_angle(nx, ny, nz):
    mag = np.sqrt(nx**2 + ny**2 + nz**2)
    return np.arccos(np.clip(ny / mag, -1.0, 1.0)) if mag > 1e-5 else 0.0


# ========================================================================
#                   Analyze one section of the coaster
# ========================================================================
# Runs every physics check that applies to this section.
# Must be given the section's arrays BEFORE they are flipped/moved into place,
# and the speed the train enters with (the exit speed of the section before it).
# Returns (stats, checks, v_exit)
def analyze_section(section_name, section_type, arrays, v_entry):
    data = empty_section_data(section_type)
    stats, checks = data["stats"], data["checks"]

    X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz = [np.ravel(arr).astype(float) for arr in arrays[:12]]

    # === Velocities through the section ===
    velocities = physics.calculate_velocity(v_entry, Y)
    stats["velocities"] = velocities

    if section_name == "Ends":
        checks["velocity_check"] = True
        v_exit = velocities[-1] if not np.isnan(velocities[-1]) else 0.0
    else:
        passed, _ = physics.velocity_check(velocities)
        checks["velocity_check"] = passed
        v_exit = velocities[-1] if passed else 0.0   # 0 = coaster stopped moving forward

    stats["velocity_exit"] = v_exit

    # === Radius through the section ===
    radius = physics.calculate_R(xyz_component=(X, Y, Z), forward_component=(Fx, Fy, Fz))
    stats["radius"] = radius

    # Top of the section
    peak_idx = np.argmax(Y)
    v_bot, v_top = velocities[0], velocities[peak_idx]   # v_bot = entry speed
    stats["v_bottom"] = v_bot
    stats["v_top"] = v_top

    # Radius at top and bottom (bottom = first curved point; replaced by the valley below for valley tracks)
    curved_idxs = np.where(radius < 1000)[0]
    bot_idx = curved_idxs[0] if len(curved_idxs) > 0 else 0
    r_top = radius[peak_idx]
    stats["r_bottom"] = radius[bot_idx]
    stats["r_top"] = r_top

    # === Valley Checks (uses the actual worst dip of the section, not the entry point) ===
    if section_type in VALLEY_CHECKS:
        valley = physics.find_valley((X, Y, Z), velocities)
        if valley is None:
            # No upward-curving dip in this section
            checks["valley_check"] = True
        else:
            valley_idx, r_valley, valley_n_y = valley
            v_valley = velocities[valley_idx]
            stats["v_bottom"] = v_valley
            stats["r_bottom"] = r_valley
            checks["valley_check"], _ = physics.valley_check(v_valley, r_valley, valley_n_y)

    # === Inversion Checks ===
    if section_type in INVERSION_CHECKS:
        checks["inversion_check"], _ = physics.inversion_check(v_top, r_top)

    # === Peak Checks ===
    elif section_type in PEAK_CHECKS:
        checks["peak_check"], _ = physics.peak_check(v_top, r_top)

    # === Lateral Checks ===
    elif section_type in LATERAL_CHECKS:
        if section_type == "Horseshoe":
            theta_rad = _bank_angle(Nx[peak_idx], Ny[peak_idx], Nz[peak_idx])
            # Displayed banking is hardcoded (the check uses theta_rad above)
            stats["deg_banking"] = 63.4

        elif section_type == "Helix":
            # The top of the helix is the first point at its furthest X
            helix_idxs = np.where(np.isclose(X, np.max(X), atol=1e-3))[0]
            top_idx = helix_idxs[0]
            theta_rad = _bank_angle(Nx[top_idx], Ny[top_idx], Nz[top_idx])
            # Displayed banking is hardcoded (the check uses theta_rad above)
            stats["deg_top"] = 45.0
            stats["deg_bottom"] = 63.4

        checks["lateral_check"], _ = physics.lateral_check(v_top, r_top, theta_rad)

    # === Ends Checks ===
    elif section_type == "Rollup":
        checks["rollup_check"], _ = physics.rollup_check(v_bot, np.max(Y))

    elif section_type == "Brake":
        track_L = np.sum(np.sqrt(np.diff(X)**2 + np.diff(Y)**2 + np.diff(Z)**2))
        checks["brake_check"], _ = physics.brake_check(v_bot, track_L)

    return stats, checks, v_exit
