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
        "deg_banking": None, "deg_top": None, "deg_bottom": None,
        # Forces the checks used, in g (so they can be checked by hand)
        "g_top": None,          # inversion: v_top^2 / (g * r_top) - 1
        "g_min": None,          # lowest seat force in the section (inversions / crests)
        "g_max": None,          # highest seat force anywhere in the section (must stay under 5 g)
        "g_valley": None,       # valley: (g * n_y + v_bottom^2 / r_bottom) / g
        "valley_ny": None,      # n_y used by the valley (1 = the dip curves straight up)
        "g_lateral": None,      # turns: worst sideways force
        "v_lateral": None, "r_lateral": None,   # speed / radius at that worst point
    }

    # Launcher and Brake sections have a fixed acceleration
    if section_type == "Launcher":
        stats["acceleration"] = 1.5
    if section_type == "Brake":
        stats["acceleration"] = -1.5

    checks = {
        "velocity_check": False,
        "max_g_check": None,
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


def _finite(value):
    value = float(value)
    return value if np.isfinite(value) else None


# Exit speed of a 'Starts' section. Frictionless, it is the track function's own v_exit.
# With friction / air resistance, the drop after the top is stepped with the losses:
#   Lift Hill: from rest at its highest point (the chain lifts it there),  Rollback: from rest at the top.
# The Launcher's speed is set by the launch motors, so it isn't changed.
def start_exit_speed(section_type, arrays, v_exit, losses=None):
    if losses is None or section_type not in ("Lift Hill", "Rollback"):
        return v_exit
    X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz = [np.ravel(arr).astype(float) for arr in arrays[:12]]
    start = int(np.argmax(Y)) if section_type == "Lift Hill" else 0
    X, Y, Z = X[start:], Y[start:], Z[start:]
    if len(X) < 2:
        return v_exit
    geometry = physics.track_geometry((X, Y, Z))
    v = physics.calculate_velocity(0.1, Y, geometry, losses)
    return float(v[-1]) if np.isfinite(v[-1]) else 0.0


# ========================================================================
#                   Analyze one section of the coaster
# ========================================================================
# Runs every physics check that applies to this section.
# Must be given the section's arrays BEFORE they are flipped/moved into place,
# and the speed the train enters with (the exit speed of the section before it).
#   losses: None = frictionless (default), or physics.make_losses(...) for friction / air resistance
# Returns (stats, checks, v_exit)
def analyze_section(section_name, section_type, arrays, v_entry, losses=None):
    data = empty_section_data(section_type)
    stats, checks = data["stats"], data["checks"]

    X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz = [np.ravel(arr).astype(float) for arr in arrays[:12]]

    # Shape of the track: direction, curvature (measured over ~2 m), rider's up/side directions
    geometry = physics.track_geometry((X, Y, Z), (Nx, Ny, Nz))
    radius = geometry["radius"]
    stats["radius"] = radius

    # === Velocities through the section ===
    # The brake slows the train at BRAKE_DECEL_G on top of any friction / air resistance
    decel = physics.BRAKE_DECEL_G * physics.G if section_type == "Brake" else 0.0
    velocities = physics.calculate_velocity(v_entry, Y, geometry, losses, decel)
    stats["velocities"] = velocities

    if section_name == "Ends":
        # The end is meant to slow / stop the train, so stopping inside it is not a failure.
        # It only fails if the train never gets here.
        checks["velocity_check"] = bool(np.isfinite(v_entry) and v_entry > 0)
        v_exit = velocities[-1] if not np.isnan(velocities[-1]) else 0.0
    else:
        passed, _ = physics.velocity_check(velocities)
        checks["velocity_check"] = passed
        v_exit = velocities[-1] if passed else 0.0   # 0 = coaster stopped moving forward

    stats["velocity_exit"] = v_exit

    # Forces on the riders at every point (in g)
    seat_g, lateral_g = physics.rider_forces(geometry, velocities)

    # === Highest force anywhere in the section (every track type) ===
    checks["max_g_check"], stats["g_max"] = physics.max_g_check(seat_g)

    # Top of the section
    peak_idx = int(np.argmax(Y))
    v_bot, v_top = velocities[0], velocities[peak_idx]   # v_bot = entry speed
    stats["v_bottom"] = v_bot
    stats["v_top"] = v_top

    # Radius at top and bottom (bottom = first curved point; replaced by the valley below for valley tracks)
    # A straight section has no radius (shown as None)
    curved_idxs = np.where(radius < 1000)[0]
    bot_idx = curved_idxs[0] if len(curved_idxs) > 0 else 0
    r_top = radius[peak_idx]
    stats["r_bottom"] = _finite(radius[bot_idx])
    stats["r_top"] = _finite(r_top)

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
            stats["r_bottom"] = _finite(r_valley)
            stats["valley_ny"] = float(valley_n_y)
            checks["valley_check"], g_valley = physics.valley_check(v_valley, r_valley, valley_n_y)
            stats["g_valley"] = _finite(g_valley / physics.G)

    # === Inversion Checks ===
    # At the top: not too fast (<= 3 g) and not too slow (v_top >= sqrt(g * r_top)),
    # and everywhere upside-down: riders stay pressed into their seats (>= 0 g)
    if section_type in INVERSION_CHECKS:
        top_ok, _ = physics.inversion_check(v_top, r_top)
        seat_ok, g_min = physics.inversion_seat_check(seat_g, geometry["N"][:, 1])
        checks["inversion_check"] = bool(top_ok and seat_ok)
        if np.isfinite(v_top) and np.isfinite(r_top) and r_top > 0:
            stats["g_top"] = float(v_top**2 / (r_top * physics.G) - 1.0)
        stats["g_min"] = g_min

    # === Peak (airtime) Checks ===
    # No point on the crest where riders are lifted out of their seats (seat force >= 0 g)
    elif section_type in PEAK_CHECKS:
        checks["peak_check"], stats["g_min"] = physics.airtime_check(seat_g)

    # === Lateral Checks ===
    # Worst sideways force anywhere in the turn (< 1.5 g); speed, radius and banking are all
    # taken at that same worst point
    elif section_type in LATERAL_CHECKS:
        passed, worst, worst_idx = physics.lateral_section_check(lateral_g)
        checks["lateral_check"] = passed
        # Turns ease in gradually, so "first curved point" isn't meaningful: show the tightest radius
        stats["r_bottom"] = _finite(np.min(radius))
        stats["g_lateral"] = worst
        if worst_idx is not None:
            stats["v_lateral"] = _finite(velocities[worst_idx])
            stats["r_lateral"] = _finite(radius[worst_idx])
            stats["deg_banking"] = float(np.degrees(_bank_angle(Nx[worst_idx], Ny[worst_idx], Nz[worst_idx])))
        if section_type == "Helix":
            # Measured from the track normals: banking at the top of the spiral (the highest point where
            # the track is turning at close to its full radius), and the steepest banking (at the bottom)
            bank = np.degrees([_bank_angle(nx, ny, nz) for nx, ny, nz in zip(Nx, Ny, Nz)])
            turning = np.where(radius < 1.1 * np.min(radius))[0]
            spiral_top = turning[np.argmax(Y[turning])] if len(turning) else peak_idx
            stats["deg_top"] = float(bank[spiral_top])
            # The highest point of a helix is the crest of the climb into the spiral, where the track
            # is almost straight (radius in the thousands of metres). Take the "top" stats at the top
            # of the spiral instead, the same point as the banking at the top.
            stats["r_top"] = _finite(radius[spiral_top])
            stats["v_top"] = velocities[spiral_top]
            stats["deg_bottom"] = float(np.max(bank))

    # === Ends Checks ===
    elif section_type == "Rollup":
        checks["rollup_check"], _ = physics.rollup_check(v_bot, np.max(Y))

    elif section_type == "Brake":
        track_L = np.sum(np.sqrt(np.diff(X)**2 + np.diff(Y)**2 + np.diff(Z)**2))
        checks["brake_check"], _ = physics.brake_check(v_bot, track_L)

    return stats, checks, v_exit
