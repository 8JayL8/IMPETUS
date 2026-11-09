# track_helpers.py
# Helper functions shared by the track part functions in tracks.py (TrackPart):
# direction / normal vectors, smooth ramps, shape building blocks, and saving / loading track CSVs.
import numpy as np
from functools import lru_cache
import file_utils


# ========================================================================
#                   Helpers shared by the track part functions
# ========================================================================
# When a prebuilt track's X positions are stretched/squashed, its front (tangent) vectors
# must be stretched the same way, otherwise the radius calculation uses the old shape.
def _stretch_front(Fx, Fy, Fz, x_stretch):
    Fx = Fx * x_stretch
    mag = np.sqrt(Fx**2 + Fy**2 + Fz**2)
    mag = np.where(mag == 0, 1.0, mag)
    return Fx / mag, Fy / mag, Fz / mag


# Front vector = step from each point to the next (the last point repeats the previous step)
def _front(X, Y, Z):
    steps = (np.diff(X), np.diff(Y), np.diff(Z))
    return tuple(np.append(d, d[-1]).astype(float) for d in steps)


# Left vector (position x front)
def _left(X, Y, Z, Fx, Fy, Fz):
    return Y * Fz - Z * Fy, Z * Fx - X * Fz, X * Fy - Y * Fx


# Normal vectors for a track that stays in the X-Y plane (rollback, rollup):
# the tangent rotated 90 degrees upward
def _planar_normals(X, Y):
    pts = len(X)
    Nx, Ny, Nz = np.zeros(pts), np.zeros(pts), np.zeros(pts)
    dx, dy = np.diff(X), np.diff(Y)

    hyp = np.sqrt(dx**2 + dy**2)
    hyp = np.where(hyp == 0, 1, hyp)  # Prevent division by zero

    Nx[:-1], Ny[:-1] = -dy / hyp, dx / hyp
    Nx[-1], Ny[-1] = Nx[-2], Ny[-2]
    return Nx, Ny, Nz


# Normal vectors for a banked 3D track (corkscrew, helix, horseshoe).
# Starts with the normal tilted by the bank angle Phi (degrees), then rotates it to follow
# the track's direction: first around Y (heading in the X-Z plane, matrix Ry), then around
# Z (climb angle, matrix Rz), i.e. N = Rz @ Ry @ N for every point.
#   forward_first: the first point's direction is the step to the second point.
#                  Otherwise it is the first point's position (as the original MATLAB code did).
# Points with no length (no direction) are left unrotated.
def _rotate_normals(X, Y, Z, Phi, forward_first=False):
    if forward_first:
        first = (X[1] - X[0], Y[1] - Y[0], Z[1] - Z[0])
    else:
        first = (X[0], Y[0], Z[0])
    dX = np.concatenate(([first[0]], np.diff(X)))
    dY = np.concatenate(([first[1]], np.diff(Y)))
    dZ = np.concatenate(([first[2]], np.diff(Z)))

    dXZ = np.sqrt(dX**2 + dZ**2)
    dS = np.sqrt(dX**2 + dY**2 + dZ**2)

    # Unrotated normal: (0, cos(Phi), -sin(Phi))
    phi = np.radians(Phi)
    n_y, n_z = np.cos(phi), -np.sin(phi)

    # Ry = [[cos_y, 0, -sin_y], [0, 1, 0], [sin_y, 0, cos_y]]
    has_xz = dXZ > 1e-9
    safe_xz = np.where(has_xz, dXZ, 1.0)
    cos_y = np.where(has_xz, dX / safe_xz, 1.0)
    sin_y = np.where(has_xz, dZ / safe_xz, 0.0)
    a, b, c = -sin_y * n_z, n_y, cos_y * n_z

    # Rz = [[cos_z, -sin_z, 0], [sin_z, cos_z, 0], [0, 0, 1]]
    has_s = dS > 1e-9
    safe_s = np.where(has_s, dS, 1.0)
    cos_z = np.where(has_s, dXZ / safe_s, 1.0)
    sin_z = np.where(has_s, dY / safe_s, 0.0)
    return cos_z * a - sin_z * b, sin_z * a + cos_z * b, c


# Positions from unit direction vectors spaced ds apart along the track (trapezoid rule), starting at 0
def _integrate_directions(T, ds):
    return np.vstack([np.zeros(3), np.cumsum(0.5 * (T[1:] + T[:-1]) * ds, axis=0)])


# Rotates each row vector v about its own axis (unit) by angle (radians) - Rodrigues' formula
def _rotate_about(v, axis, angle):
    c, s = np.cos(angle)[:, None], np.sin(angle)[:, None]
    return v * c + np.cross(axis, v) * s + axis * np.sum(axis * v, axis=1)[:, None] * (1 - c)


# Carries an up vector along a track without twisting it (rotation-minimising frame,
# "double reflection" method). P: points, T: unit directions, N0: up vector at the first point.
def _carry_normal(P, T, N0):
    N = np.zeros_like(P)
    N[0] = N0
    for i in range(1, len(P)):
        v1 = P[i] - P[i - 1]
        c1 = v1 @ v1
        r = N[i - 1] - (2 / c1) * (v1 @ N[i - 1]) * v1
        t = T[i - 1] - (2 / c1) * (v1 @ T[i - 1]) * v1
        v2 = T[i] - t
        c2 = v2 @ v2
        N[i] = r - (2 / c2) * (v2 @ r) * v2 if c2 > 1e-14 else r
    return N


# Cobra roll shape with a top radius of 1 (see TrackPart.cobrarollCG_func). It doesn't depend on
# the size, so it is worked out once per neck height / neck radius and cached.
#   neck_radius: radius of the dip at the neck, as a multiple of the top radius. The train is much
#   faster at the neck than at the top, so a neck as tight as the top always went over 5 g.
@lru_cache(maxsize=8)
def _cobra_unit_shape(neck_fraction, neck_radius=2.0, n_fine=20001):
    u = np.linspace(0, 1, n_fine)

    # 1. Half loop: pitch angle = pi * u^2, so curvature rises linearly from 0 to 1 (an Euler spiral)
    loop_length = 2 * np.pi
    pitch = np.pi * u**2
    T_loop = np.column_stack((np.cos(pitch), np.sin(pitch), np.zeros_like(u)))
    P_loop = _integrate_directions(T_loop, loop_length / (n_fine - 1))
    top_height = P_loop[-1, 1]

    # 2. Half corkscrew: heading turns from -X to -Z (smoothly) while it dives and levels out.
    #    The dive angle follows a cubic (Hermite) curve, chosen so that the curvature is
    #      - 1 where it leaves the top (the same as the top of the half loop: no jolt), and
    #      - 1 / neck_radius at the neck, where it pulls out of the dive (a wider, gentler dip).
    #    Its length sets how deep it dives.
    def half_corkscrew(length):
        heading = (np.pi / 2) * (3 * u**2 - 2 * u**3)
        dive = -length * (u**3 - 2 * u**2 + u) + (length / neck_radius) * (u**3 - u**2)
        T = np.column_stack((-np.cos(dive) * np.cos(heading), np.sin(dive), -np.cos(dive) * np.sin(heading)))
        return length, T, _integrate_directions(T, length / (n_fine - 1))

    # Find the length that puts the neck at neck_fraction of the height (bisection)
    low, high = 0.5, 40.0
    for _ in range(60):
        length = 0.5 * (low + high)
        _, _, P_try = half_corkscrew(length)
        if top_height + P_try[-1, 1] > neck_fraction * top_height:
            low = length
        else:
            high = length
    cork_length, T_cork, P_cork = half_corkscrew(length)
    P_cork = P_cork + P_loop[-1]
    for arr in (P_loop, T_loop, P_cork, T_cork):
        arr.flags.writeable = False   # shared by every call: make sure nothing changes them
    return P_loop, T_loop, loop_length, P_cork, T_cork, cork_length


# Normal vectors for a track that turns toward -Z while heading +X (e.g. the horseshoe),
# banked by Phi degrees toward the centre of the turn.
# Starts from "straight up, square to the track", then tilts it about the direction of travel.
# Works for any heading and climb (unlike _rotate_normals, which assumes the climb is about world Z).
def _banked_normals(X, Y, Z, Phi):
    P = np.column_stack((X, Y, Z)).astype(float)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    up = np.array([0.0, 1.0, 0.0]) - T[:, 1:2] * T     # world up, made square to the track
    up /= np.linalg.norm(up, axis=1)[:, None]
    inward = np.cross(up, T)                            # toward the centre of the turn (-Z when heading +X)
    phi = np.radians(Phi)[:, None]
    N = np.cos(phi) * up + np.sin(phi) * inward
    return N[:, 0], N[:, 1], N[:, 2]


# 0 -> 1 as s goes 0 -> 1, with zero slope and zero curvature at both ends
# (so a height change built with it joins flat track with no sudden change in G-force)
def _smootherstep(s):
    return 10 * s**3 - 15 * s**4 + 6 * s**5


# Smooth ramp from flat ground up to height y_end, arriving with slope slope_end.
# Quintic curve: starts flat with no curvature, and ends at the right slope with no curvature,
# so it joins flat track and the next shape without a kink or a sudden change in G-force.
def _smooth_ramp(y_end, slope_end, length, pts=120):
    s = np.linspace(0, 1, pts)
    rise = 10 * s**3 - 15 * s**4 + 6 * s**5      # goes 0 -> 1, flat at both ends
    tilt = -4 * s**3 + 7 * s**4 - 3 * s**5       # adds the end slope, flat at both ends
    return s * length, y_end * rise + slope_end * length * tilt


# Tightest bend (smallest radius) of a curve in the X-Y plane
def _min_radius_xy(X, Y):
    dx, dy = np.gradient(X), np.gradient(Y)
    ddx, ddy = np.gradient(dx), np.gradient(dy)
    curvature = np.abs(dx * ddy - dy * ddx) / (dx**2 + dy**2) ** 1.5
    return 1 / np.max(curvature[2:-2])


# The shortest ramp whose tightest bend is at least target_radius.
# If the rise is too small for that, the gentlest ramp that still never climbs above y_end
# (a longer ramp would overshoot and come back down).
def _gentle_ramp(y_end, slope_end, target_radius):
    best = None
    length = max(y_end / slope_end, 1.0)
    while length < 400:
        X, Y = _smooth_ramp(y_end, slope_end, length)
        if np.all(np.diff(Y) >= -1e-9) and Y.max() <= y_end + 1e-6:
            radius = _min_radius_xy(X, Y)
            if best is None or radius > best[2]:
                best = (X, Y, radius)
            if radius >= target_radius:
                break
        length *= 1.04
    return best[0], best[1]


# Saves a track part's segment CSV and returns its track content tuple
def _finish(file_name, prop, X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz):
    pts = len(X)
    data = np.column_stack((np.arange(1, pts+1), X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz))
    file_utils.write_csv(data, pts, prop, file_name)
    return (X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz, file_name)


# Same as _finish, but works out the front and left vectors from the positions
def _build(file_name, prop, X, Y, Z, Nx, Ny, Nz):
    Fx, Fy, Fz = _front(X, Y, Z)
    Lx, Ly, Lz = _left(X, Y, Z, Fx, Fy, Fz)
    return _finish(file_name, prop, X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz)


# Makes a flat (X-Y plane) track symmetric about its highest point: the second half is replaced
# by a mirror image of the first half, so the train comes out the same way it went in.
def _mirror_about_crest(X, Y):
    c = int(np.argmax(Y))
    X = np.concatenate([X[:c + 1], 2 * X[c] - X[c - 1::-1]])
    Y = np.concatenate([Y[:c + 1], Y[c - 1::-1]])
    return X, Y


# Bends the first and last few metres of a flat (X-Y plane) track very slightly so it starts and
# ends exactly level, keeping the end heights. Without this, a track that ends while still
# sloping leaves a kink where the next section starts (a jolt the riders would feel).
# The correction is a cubic that is 0 at both ends of the stretch it changes, so nothing jumps.
def _level_ends(X, Y, blend=10.0):
    X, Y = X.astype(float), Y.astype(float).copy()
    blend = min(blend, 0.15 * (X[-1] - X[0]))
    slope_start = (Y[1] - Y[0]) / (X[1] - X[0])
    slope_end = (Y[-1] - Y[-2]) / (X[-1] - X[-2])

    t = (X - X[0]) / blend                                # 0 -> 1 over the first `blend` metres
    first = t < 1
    Y[first] -= slope_start * blend * (t[first]**3 - 2 * t[first]**2 + t[first])

    t = (X - (X[-1] - blend)) / blend                     # 0 -> 1 over the last `blend` metres
    last = t > 0
    Y[last] -= slope_end * blend * (t[last]**3 - t[last]**2)
    return X, Y


# Reads a prebuilt track (from Prebuilt_tracks/), scales it so its max height is h,
# and stretches its X by x_stretch.
#   tidy=True (for the flat lift hill / camelback shapes): starts and ends the track exactly level,
#   optionally makes it symmetric (mirror=True), and works out the front / up vectors again from
#   the final shape, so the saved segment matches the track that is actually used.
def _load_prebuilt(csv_name, h, x_stretch, file_name, tidy=False, mirror=False):
    if tidy:
        data = file_utils.read_csv(csv_name)
        scale = h / np.max(data[:, 2])
        X, Y = data[:, 1] * scale * x_stretch, data[:, 2] * scale
        if mirror:
            X, Y = _mirror_about_crest(X, Y)
        X, Y = _level_ends(X, Y)
        Z = np.zeros_like(X)
        Nx, Ny, Nz = _planar_normals(X, Y)
        return _build(file_name, h, X, Y, Z, Nx, Ny, Nz)

    data = file_utils.read_csv(csv_name)
    track = data.copy()

    # Scales the track based on your input height
    track[:, 1:4] = track[:, 1:4] * h / np.max(data[:, 2])

    X, Y, Z = track[:, 1] * x_stretch, track[:, 2], track[:, 3]
    if x_stretch == 1:
        Fx, Fy, Fz = track[:, 4], track[:, 5], track[:, 6]
    else:
        Fx, Fy, Fz = _stretch_front(track[:, 4], track[:, 5], track[:, 6], x_stretch)
    Lx, Ly, Lz = track[:, 7], track[:, 8], track[:, 9]
    Nx, Ny, Nz = track[:, 10], track[:, 11], track[:, 12]

    file_utils.write_csv(track, len(track), h, file_name)
    return (X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz, file_name)
