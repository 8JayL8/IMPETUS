import numpy as np


# Physics calculations and safety checks used by section_checks.analyze_section
G = 9.8   # gravity (m/s^2)

def calculate_velocity(v_exit, Y_array):
    # Check if the exit velocity from the previous track part is sufficient to navigate the next track part
    # This can be done by calculating the required velocity to navigate the next track part and comparing it to the exit velocity
    delta_y = Y_array - Y_array[0]
    v_squared = (v_exit ** 2) - (2 * G * delta_y)

    with np.errstate(invalid='ignore'):
        velocity_array = np.sqrt(v_squared)

    return velocity_array

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
    a_decel = 1.5
    v_max = np.sqrt(2 * a_decel * G * L)
    if v_bot > v_max:
        return False, v_max
    return True, v_max
