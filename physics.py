import numpy as np


# Physics calculations and safety checks used by section_checks.analyze_section
G = 9.8   # gravity (m/s^2)
BRAKE_DECEL_G = 1.5   # brake deceleration, in g (used by the brake speed and the brake check)
AIR_DENSITY = 1.225   # kg/m^3, sea level


# ========================================================================
#                       Energy losses (friction + air)
# ========================================================================
# losses = None (frictionless, the default) or a dict:
#   "mu":    rolling-friction coefficient: friction force = mu * (force pressing the wheels on the track)
#   "k_air": air drag per unit mass (1/m): drag deceleration = k_air * v^2
#            k_air = 0.5 * air density * drag coefficient * frontal area / train mass
def make_losses(mu=0.0, drag_coefficient=0.0, frontal_area=0.0, mass=1.0):
    k_air = 0.5 * AIR_DENSITY * drag_coefficient * frontal_area / mass if mass > 0 else 0.0
    if mu <= 0 and k_air <= 0:
        return None
    return {"mu": float(max(mu, 0.0)), "k_air": float(max(k_air, 0.0))}


def calculate_velocity(v_exit, Y_array, geometry=None, losses=None, decel=0.0):
    # Speed at every point of a section, starting with speed v_exit (the previous section's exit speed).
    #   Frictionless (losses=None, decel=0):  v^2 = v_entry^2 - 2*g*(y - y_entry)
    #   Otherwise it is stepped along the track: each step also loses
    #     2 * (mu * wheel force + k_air * v^2 + decel) * step length
    #   decel: extra constant deceleration in m/s^2 (brakes)
    # NaN from the point where the train runs out of speed.
    Y_array = np.asarray(Y_array, dtype=float)
    if losses is None and decel == 0:
        delta_y = Y_array - Y_array[0]
        v_squared = (v_exit ** 2) - (2 * G * delta_y)
        with np.errstate(invalid='ignore'):
            return np.sqrt(v_squared)

    if geometry is None:
        raise ValueError("geometry is needed when there are energy losses")
    mu = losses["mu"] if losses else 0.0
    k_air = losses["k_air"] if losses else 0.0

    # Plain Python floats in the loop (much faster than numpy element by element)
    s = geometry["s"].tolist()
    kx, ky, kz = (geometry["curvature"][:, c].tolist() for c in range(3))
    tx, ty, tz = (geometry["T"][:, c].tolist() for c in range(3))
    y = Y_array.tolist()
    n = len(y)
    out = [float("nan")] * n
    v2 = float(v_exit) ** 2
    out[0] = np.sqrt(v2)
    for i in range(1, n):
        ds = s[i] - s[i - 1]
        loss = decel
        if mu > 0:
            # force the track pushes on the train (per kg) = centripetal + holding it up against gravity,
            # minus the part along the track
            fx, fy, fz = v2 * kx[i - 1], v2 * ky[i - 1] + G, v2 * kz[i - 1]
            along = fx * tx[i - 1] + fy * ty[i - 1] + fz * tz[i - 1]
            px, py, pz = fx - along * tx[i - 1], fy - along * ty[i - 1], fz - along * tz[i - 1]
            loss += mu * (px * px + py * py + pz * pz) ** 0.5
        loss += k_air * v2
        v2 = v2 - 2 * G * (y[i] - y[i - 1]) - 2 * loss * ds
        if v2 < 0:
            break   # train stopped: the rest stays NaN
        out[i] = v2 ** 0.5
    return np.array(out)


# ========================================================================
#               Track geometry + forces felt by the riders
# ========================================================================
# Direction of travel, curvature and the rider's up/side directions at every point.
# Curvature is measured over ~`window` metres of track (not point to point), so
# duplicate points at joins and uneven point spacing don't create fake tiny radii.
def track_geometry(xyz_component, normals=None, window=2.0):
    pos_all = np.column_stack(xyz_component).astype(float)
    n_all = len(pos_all)

    # Work on the points with no duplicates, then copy the results back to every point
    step = np.linalg.norm(np.diff(pos_all, axis=0), axis=1)
    keep_mask = np.r_[True, step > 1e-9]
    keep = np.where(keep_mask)[0]
    back = np.cumsum(keep_mask) - 1          # index into the kept points, for every point
    pos = pos_all[keep]
    n = len(pos)

    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pos, axis=0), axis=1))]
    if n < 3:
        T = np.tile([1.0, 0.0, 0.0], (n, 1))
        curvature = np.zeros((n, 3))
        radius = np.full(n, np.inf)
    else:
        # Points about window/2 behind and ahead (at least the neighbouring points)
        idx = np.arange(n)
        lo = np.searchsorted(s, s - window / 2, side="left")
        hi = np.searchsorted(s, s + window / 2, side="right") - 1
        lo = np.clip(np.minimum(lo, idx - 1), 0, n - 1)
        hi = np.clip(np.maximum(hi, idx + 1), 0, n - 1)

        # Direction of travel: from the point behind to the point ahead
        T = pos[hi] - pos[lo]
        T = T / np.where(np.linalg.norm(T, axis=1) == 0, 1.0, np.linalg.norm(T, axis=1))[:, None]

        # Curvature from the circle through (behind, this point, ahead). This is exact for points on
        # a circle however unevenly they are spaced (some track parts are spaced evenly in X, so
        # their points are far apart around tight curves).
        a = pos[lo] - pos
        b = pos[hi] - pos
        axb = np.cross(a, b)
        denom = 2 * np.sum(axb**2, axis=1)
        num = np.cross(np.sum(a**2, axis=1)[:, None] * b - np.sum(b**2, axis=1)[:, None] * a, axb)
        straight = denom < 1e-12 * np.maximum(np.sum(a**2, axis=1) * np.sum(b**2, axis=1), 1e-30)
        with np.errstate(divide="ignore", invalid="ignore"):
            to_centre = np.where(straight[:, None], 0.0, num / np.where(denom == 0, 1, denom)[:, None])
            r2 = np.sum(to_centre**2, axis=1)
            radius = np.where(straight, np.inf, np.sqrt(r2))
            # curvature vector: points to the centre of the bend, length 1/radius
            curvature = np.where(straight[:, None], 0.0, to_centre / np.where(r2 == 0, 1, r2)[:, None])

    geometry = {
        "s": np.r_[0, np.cumsum(np.r_[step])] if n_all > 1 else np.zeros(1),
        "T": T[back], "curvature": curvature[back], "radius": radius[back],
    }

    # Rider's up (track normal, made square to the track) and side directions
    if normals is not None:
        N = np.column_stack(normals).astype(float)
        N = N - np.sum(N * geometry["T"], axis=1)[:, None] * geometry["T"]
        mag = np.linalg.norm(N, axis=1)
        bad = mag < 1e-6
        N[bad] = [0.0, 1.0, 0.0]
        mag[bad] = 1.0
        N = N / mag[:, None]
        geometry["N"] = N
        geometry["side"] = np.cross(geometry["T"], N)
    return geometry


# Forces the riders feel at every point, in g:
#   seat:    along the rider's up direction (+1 = normal weight, 0 = weightless, < 0 = lifted out of the seat)
#   lateral: sideways (pushed toward the rider's left/right)
# felt force = (centripetal acceleration) - (gravity) = v^2 * curvature + (0, g, 0)
def rider_forces(geometry, velocities):
    v2 = np.asarray(velocities, dtype=float) ** 2
    f = v2[:, None] * geometry["curvature"] + np.array([0.0, G, 0.0])
    seat = np.sum(f * geometry["N"], axis=1) / G
    lateral = np.sum(f * geometry["side"], axis=1) / G
    return seat, lateral

def calculate_R(xyz_component, forward_component):
    X, Y, Z = xyz_component
    Fx, Fy, Fz = forward_component

    # delta_S = np.sqrt(delta_x**2 + delta_y**2 + delta_z**2)
    position = np.column_stack((X,Y,Z))
    delta_position = np.diff(position, axis=0)
    delta_S = np.linalg.norm(delta_position, axis=1)

    # delta_theta = arccos((F1xF2x + F1yF2y + F1zF2z) / (|F1| * |F2|))
    forces = np.column_stack((Fx,Fy,Fz))

    F_current = forces[:-1]
    F_next = forces[1:]
    dot_product = np.sum(F_current * F_next, axis = 1)

    mag_current = np.linalg.norm(F_current, axis = 1)
    mag_next = np.linalg.norm(F_next, axis = 1)
    mag_product = mag_current * mag_next
    mag_product = np.where(mag_product == 0, 1e-12, mag_product)

    cos_theta = dot_product / mag_product
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    delta_theta = np.arccos(cos_theta)

    # radius = delta_S / delta_theta
    with np.errstate(divide='ignore', invalid='ignore'):
        radius = np.where(delta_theta == 0, np.inf, delta_S / delta_theta)
    # Add another last element of the radius array to the end so it matches length of velocities
    radius = np.append(radius, radius[-1])

    # print(f"{section} section's radius: {radius}")
    return radius

def velocity_check(velocity_array):
    if np.isnan(velocity_array).any():
        first_fail_idx = np.where(np.isnan(velocity_array))[0][0]
        return False, first_fail_idx
    return True, None

def find_valley(xyz_component, velocities, window=2.0, low_fraction=0.25):
    # Finds the worst valley of a section: the low part of the track where it curves upward
    # and pushes riders hardest into their seats (e.g. entry/exit dips of a camelback or loop).
    #   - Only points in the lowest `low_fraction` of the section's height range are considered.
    #   - Curvature is measured over ~`window` meters of track using the point positions, so
    #     duplicate points at joins or bad front vectors in the CSVs don't create fake tiny radii.
    # Returns (index, radius, n_y) or None if the section has no valley.
    #   n_y = how straight up the curve bends (1 = bottom of a dip, 0 = sideways)
    X, Y, Z = xyz_component
    pos = np.column_stack((X, Y, Z)).astype(float)
    v = np.asarray(velocities, dtype=float)

    # Drop zero-length (duplicate) points
    step = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    keep = np.r_[0, np.where(step > 1e-9)[0] + 1]
    pos, v = pos[keep], v[keep]
    if len(pos) < 3:
        return None

    # Unit tangent (direction of travel) from neighbouring points
    T = np.gradient(pos, axis=0)
    T_mag = np.linalg.norm(T, axis=1)
    T = T / np.where(T_mag == 0, 1.0, T_mag)[:, None]

    # Compare tangents ~window/2 behind and ahead of each point
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pos, axis=0), axis=1))]   # arc length
    n = len(s)
    idx = np.arange(n)
    lo = np.searchsorted(s, s - window / 2, side="left")
    hi = np.searchsorted(s, s + window / 2, side="right") - 1
    # Always reach at least one neighbour on each side (for coarsely spaced tracks)
    lo = np.clip(np.minimum(lo, idx - 1), 0, n - 1)
    hi = np.clip(np.maximum(hi, idx + 1), 0, n - 1)
    arc = s[hi] - s[lo]
    dT = T[hi] - T[lo]
    angle = np.arccos(np.clip(np.sum(T[hi] * T[lo], axis=1), -1.0, 1.0))

    with np.errstate(divide="ignore", invalid="ignore"):
        radius = np.where(angle > 1e-9, arc / angle, np.inf)
        n_y = dT[:, 1] / np.linalg.norm(dT, axis=1)
        g_valley = G * n_y + v**2 / radius

    y = pos[:, 1]
    is_low = y <= y.min() + low_fraction * (y.max() - y.min())
    candidates = np.where(is_low & (n_y > 0) & np.isfinite(g_valley))[0]
    if len(candidates) == 0:
        return None

    j = candidates[np.argmax(g_valley[candidates])]
    return keep[j], radius[j], n_y[j]

def valley_check(v_bot, r_1, n_y=1.0):
    # Force pushing riders into their seats at the bottom of a valley: g * n_y + v^2 / r
    # (n_y = 1 when the dip curves straight up, i.e. the classic g + v^2 / r)
    # Fails if it reaches 5g.
    if np.isnan(v_bot) or np.isnan(r_1):
        return False, 0.0

    g_valley = G * n_y + (v_bot**2 / r_1)
    if g_valley >= (5 * G):
        return False, g_valley
    return True, g_valley

def inversion_check(v_at_ymax, r_at_ymax):
    if np.isnan(v_at_ymax) or np.isnan(r_at_ymax):
        return False, 0.0

    if r_at_ymax <= 1e-3:
        return False, 0.0

    # This ensures that they aren't going too fast at the top of the inversion
    g_top = (v_at_ymax**2 / (r_at_ymax * G)) - 1.0
    max_allowed_g = 3.0  # Limit for comfortable inverted peaks
    if g_top > max_allowed_g:
        return False, g_top

    # This ensures that they aren't going too slow at the top of the inversion
    v_min = np.sqrt(r_at_ymax * G)
    if v_at_ymax < v_min:
        return False, v_min
    return True, v_min


def peak_check(v_at_max, r_at_ymax):
    if np.isnan(v_at_max) or np.isnan(r_at_ymax):
        return False, 0.0

    if r_at_ymax <= 1e-3:
        return False, 0.0

    v_max = np.sqrt(r_at_ymax * G)
    if v_at_max > v_max:
        return False, v_max
    return True, v_max

# ===== Whole-section checks (every point, not just the top) =====
# These use rider_forces(); a point the train never reaches (NaN speed) is skipped.

# Upside-down part of an inversion (rider's up points below horizontal):
# riders must stay pressed into the seat everywhere (seat force >= 0 g).
def inversion_seat_check(seat_g, normal_y):
    inverted = (normal_y < 0) & np.isfinite(seat_g)
    if not inverted.any():
        return True, None
    worst = float(np.min(seat_g[inverted]))
    return worst >= 0.0, worst


# Crest (airtime) check: no point where riders are lifted out of their seats (seat force < 0 g).
# Riders must be pushed into their seats with less than 5 g at EVERY point of the section.
# valley_check only looks at the lowest dip, so a tight bend higher up (e.g. the "neck" in the
# middle of a cobra roll) could go over 5 g without failing anything.
# Returns (passed, highest seat force in g)
MAX_SEAT_G = 5.0


def max_g_check(seat_g):
    ok = np.isfinite(seat_g)
    if not ok.any():
        return True, None   # the train never moves through this section (velocity_check covers that)
    worst = float(np.max(seat_g[ok]))
    return worst < MAX_SEAT_G, worst


def airtime_check(seat_g):
    ok = np.isfinite(seat_g)
    if not ok.any():
        return False, None
    worst = float(np.min(seat_g[ok]))
    return worst >= 0.0, worst


# Sideways force must stay under 1.5 g at every point of the turn.
# Returns (passed, worst lateral g with its sign, index of the worst point)
def lateral_section_check(lateral_g):
    ok = np.isfinite(lateral_g)
    if not ok.any():
        return False, None, None
    idx = int(np.nanargmax(np.where(ok, np.abs(lateral_g), -1)))
    worst = float(lateral_g[idx])
    return abs(worst) <= 1.5, worst, idx


# Single-point formula: (v^2 / R) * cos(theta) - g * sin(theta), for a level banked turn
def lateral_check(v_top, r, theta_rad):
    # (v_top^2 / R) * cos(theta) - g * sin(theta) < 1.5g
    if np.isnan(v_top) or np.isnan(r) or np.isnan(theta_rad):
        return False, 0.0

    if r <= 1e-3:
        return False, 0.0

    lat_accel = ((v_top**2 / r) * np.cos(theta_rad)) - (G * np.sin(theta_rad))
    max_allowed = 1.5 * G

    if np.abs(lat_accel) > max_allowed:
        return False, lat_accel / G
    return True, lat_accel / G

def rollup_check(v_bot, h):
    if np.isnan(v_bot) or np.isnan(h):
        return False, 0.0

    # h_climb = (v_bot^2 / 2g)
    h_climb = (v_bot**2) / (2 * G)
    # Need the h_climb to be larger
    if h < h_climb:
        return False, h_climb
    return True, h_climb

def brake_check(v_bot, L):
    if np.isnan(v_bot) or np.isnan(L):
        return False, 0.0

    # v_max = sqrt(2 * a * L), check if v_bot < v_max
    v_max = np.sqrt(2 * BRAKE_DECEL_G * G * L)
    if v_bot > v_max:
        return False, v_max
    return True, v_max
