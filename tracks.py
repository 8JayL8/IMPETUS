import numpy as np
import file_utils
import section_checks   # All physics checks for each section (uses physics.py)
from physics import G   # gravity (m/s^2)
import matplotlib.pyplot as plt
# Helpers shared by the track part functions (vectors, ramps, building / saving a part)
from track_helpers import (
    _left, _planar_normals, _rotate_normals, _banked_normals, _smootherstep,
    _rotate_about, _carry_normal, _cobra_unit_shape, _gentle_ramp,
    _finish, _build, _load_prebuilt,
)

INVERT_TRACKS = ["Thrills 2", "Ends"]   # Inverted tracks


# This class is used to store all track part functions
# For all tracks, friction is negligible.
class TrackPart:
    # This is used to initialize the TrackPart class
    # Could be used to later connect different track parts together
    # For now, it just stores the output of each track part function
    def __init__(self, **kwargs):
        attr = ['X', 'Y', 'Z', 'Fx', 'Fy', 'Fz', 'Lx', 'Ly', 'Lz', 'Nx', 'Ny', 'Nz', 'file_name']
        for key in attr:
            setattr(self, key, kwargs.get(key, None))

    # ========================== Any track given data ==========================
    # Given data (csv file) of a real track, this function will read the data and return the track
    # part which is scaled, based on the user input.
    @staticmethod
    def from_data(scale, track_name):
        return _load_prebuilt(f"{track_name}.csv", scale, 3, track_name)


    # ========================================================================
    #                               Start Tracks
    # ========================================================================
    # Launcher track part (done)
    @staticmethod
    def launcher_func(L):
        X = np.arange(0, L+1, 1)
        pts = len(X)
        Y, Z = np.zeros(pts), np.zeros(pts)
        Nx, Ny, Nz = np.zeros(pts), np.ones(pts), np.zeros(pts)
        track_content = _build("launcher", L, X, Y, Z, Nx, Ny, Nz)

        # v_exit = sqrt(2 * 1.5g * L) where a is the acceleration and L is the length of the track
        v_exit = np.sqrt(2 * 1.5 * G * L) # Assuming a constant acceleration of 1.5g for the launcher
        return track_content, v_exit

    # Lifthill track part (checked)
    @staticmethod
    def lifthill_func(h):
        # h is the max height
        # tidy: the file's track ends still sloping down ~1 degree; make it end level (no kink into the next section)
        track_content = _load_prebuilt("cometlifthill.csv", h, 1, "lifthill", tidy=True)
        max_y = np.max(track_content[1])
        v_exit = np.sqrt(2 * G * max_y)
        return track_content, v_exit

    # Rollback track part (done)
    @staticmethod
    def rollback_func(h):
        R = (2 / 3) * h

        tan_60 = np.tan(np.radians(60))
        sin_60 = np.sin(np.radians(60))

        max_x1 = (2 * h) / (3 * tan_60)
        Xc = max_x1 + R * sin_60

        # Track section lengths
        station_length = 15
        final_flat_length = 15

        total_x_length = int(np.floor(Xc)) + station_length + final_flat_length

        X = np.arange(0, total_x_length + 1, 1, dtype=float)
        # Y of each part: slope, then curve, then flat at 0 (station and final flat)
        Y = np.select(
            [X <= max_x1, X <= Xc],
            [h - tan_60 * X, R - np.sqrt(np.clip(R**2 - (X - Xc)**2, 0, None))],
            default=0.0,
        )
        Z = np.zeros_like(X)

        Nx, Ny, Nz = _planar_normals(X, Y)
        track_content = _build("rollback", h, X, Y, Z, Nx, Ny, Nz)
        v_exit = np.sqrt(2 * G * h)
        return track_content, v_exit


    # ========================================================================
    #                               Thrill Tracks
    # ========================================================================
    # Camelback track part (done)
    @staticmethod
    def camelback_func(h):
        # The file's descent is cut short (13 m shorter than the climb, still sloping down when it ends),
        # which made a tighter dip and a kink into the next section. Use the climb mirrored as the descent.
        return _load_prebuilt("cometcamelback.csv", h, 1 / 3, "camelback", tidy=True, mirror=True)

    # Corkscrew track part (done)
    @staticmethod
    # h = height of each barrel (both barrels are h tall, i.e. barrel radius = h/2)
    def corkscrew_func(h):
        R = h / 2               # barrel radius
        clearance = 1.0         # barrel bottom stays this far off the ground (was 0: it dipped to the ground)
        Yc = R + clearance      # height of the barrel's centre line (the max height is h + clearance)
        b = 0.7 * h             # forward distance per radian of roll (pitch = 2*pi*b per full roll),
                                # in proportion to h so every size has the same shape
        valley_radius = 30.0    # aim for entry/exit bends at least this wide (keeps the valley G-force down)

        # Section 1 (lead-in): smooth ramp from the ground up to the side of the barrel,
        # arriving at the barrel's starting slope (dY/dX = R / b)
        X1, Y1 = _gentle_ramp(Yc, R / b, valley_radius)
        l1 = X1[-1]
        Z1 = np.zeros_like(X1)
        t_norm1 = np.linspace(0, 1, len(X1))
        Phi1 = -90 * (0.5 - 0.5 * np.cos(np.pi * t_norm1))

        # Section 2 (the barrels): 1.5 rolls around the centre line, two inversions
        # linspace so the barrel ends exactly at 3*pi (arange stopped at 9.42, leaving a 3 cm step into the exit)
        t = np.linspace(0, 3 * np.pi, int(np.ceil(3 * np.pi / 0.01)) + 1)
        X2 = b * t + l1
        Y2 = Yc + R * np.sin(t)
        Z2 = R * (1 - np.cos(t))   # rolls to the side so the track doesn't turn into itself
        Phi2 = -90 - (540 / (3 * np.pi)) * t

        # Section 3 (exit): mirror image of the lead-in, back down to the ground
        X3 = X2[-1] + (l1 - X1[::-1])
        Y3 = Y1[::-1]
        Z3 = np.full_like(X1, Z2[-1])
        Phi3 = -Phi1[::-1]

        # Combines the three sections into one (dropping the repeated joining points)
        X = np.concatenate([X1, X2[1:], X3[1:]])
        Y = np.concatenate([Y1, Y2[1:], Y3[1:]])
        Z = np.concatenate([Z1, Z2[1:], Z3[1:]])
        Phi = np.concatenate([Phi1, Phi2[1:], Phi3[1:]])

        Nx, Ny, Nz = _rotate_normals(X, Y, Z, Phi)
        return _build("corkscrew", h, X, Y, Z, Nx, Ny, Nz)

    # Loop with constant G-force (checked)
    @staticmethod
    def loopCG_func(h):
        ngs = 4
        # Use a baseline initial height H to generate the characteristic shape
        H_initial = h * 1.5
        dt = 0.01

        # Initialize conditions
        X, Y, S, V = [0], [0], [0], [np.sqrt(2 * G * H_initial)]
        Nx, Ny, Nz, theta = [0], [1], [0], [0]
        R = [V[0]**2 / (G * (ngs - np.cos(theta[0])))]

        go = 1
        i = 1

        while go < 3:
            # arc length
            S.append(S[i-1] + V[i-1] * dt)
            # angle increment
            theta.append(theta[i-1] + (S[i] - S[i-1]) / R[i-1])
            # positions
            Y.append(Y[i-1] + (S[i] - S[i-1]) * np.sin(theta[i]))
            X.append(X[i-1] + (S[i] - S[i-1]) * np.cos(theta[i]))
            # velocity update
            V.append(np.sqrt(V[i-1]**2 - 2 * G * (Y[i] - Y[i-1])))
            # radius of curvature
            R.append(V[i]**2 / (G * (ngs - np.cos(theta[i]))))
            # normal vectors
            Nx.append(-np.sin(theta[i]))
            Ny.append(np.cos(theta[i]))
            Nz.append(0)

            if (Y[i] - Y[i-1]) < 0:
                go = 2
            if go == 2 and (Y[i] - Y[i-1]) >= 0:
                go = 3

            i += 1

        # Scale the loop so its peak is exactly h
        X, Y = np.array(X), np.array(Y)
        scale_factor = h / np.max(Y)
        X = X * scale_factor
        Y = Y * scale_factor

        Nx, Ny, Nz = np.array(Nx), np.array(Ny), np.array(Nz)

        # Side (Z) offset so the exit track passes beside the entry track instead of through it.
        # It grows with the loop's height (25% of h), but is never less than the original 2 m.
        z_offset = max(0.25 * h, 2.0)
        xx = np.arange(1, len(X)+1)
        Z = (z_offset / 2) * (np.cos((np.pi / max(xx)) * xx) - 1)

        # Front vector here is 0 at the last point
        Fx, Fy, Fz = np.diff(X, append=X[-1]), np.diff(Y, append=Y[-1]), np.diff(Z, append=Z[-1])
        Lx, Ly, Lz = _left(X, Y, Z, Fx, Fy, Fz)
        return _finish("loopCG", h, X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz)

    # Loop with 2 different radii (TODO - later)
    @staticmethod
    def loopwith2Rs(r1, r2):
        return None


    # ========================================================================
    #                               Turn Tracks
    # ========================================================================
    # Cobra Roll track part, built from equations (h = height of the two tops)
    # Two inversions; the train leaves heading back the way it came, offset to the side.
    #   First half:
    #     1. Half loop: an Euler spiral (clothoid). Its curvature grows steadily from 0 (so it starts
    #        smoothly from flat track) up to 1/r_top at the top, where the train is upside-down heading -X.
    #     2. Half corkscrew: dives and turns 90 degrees (heading -X -> -Z) down to the "neck",
    #        rolling back upright. It starts with the same curvature as the top of the half loop (no jolt),
    #        and pulls out of the dive into the neck on a radius neck_radius times the top radius.
    #        (The train is fastest at the neck: when the neck was as tight as the top, riders felt
    #        over 5 g there at every size.)
    #   Second half: the first half mirrored about the neck and run backwards, so the two halves meet
    #   smoothly at the neck and the exit heads -X.
    @staticmethod
    def cobrarollCG_func(h):
        # Old version: loaded a prebuilt CSV. Half of its direction vectors pointed the wrong way,
        # and stretching it 3x in X tilted its up vectors by up to 30 degrees.
        # return _load_prebuilt("flashbackcobraroll.csv", h, 3, "cobrarollCG")

        neck_fraction = 0.35   # neck height as a fraction of the top height
        neck_radius = 2.0      # radius of the dip at the neck, as a multiple of the top radius
        step = 0.3             # point spacing (m)

        # Shape with a top radius of 1 (the same for every h, so it is worked out once and reused)
        P_loop, T_loop, loop_length, P_cork, T_cork, cork_length = _cobra_unit_shape(neck_fraction, neck_radius)
        top_height = P_loop[-1, 1]
        n_fine = len(P_loop)

        # Resample both pieces evenly (about `step` metres apart) at full size
        scale = h / top_height        # = top radius in metres
        def resample(P, T, length):
            n = max(int(np.ceil(length * scale / step)), 20)
            idx = np.linspace(0, n_fine - 1, n + 1)
            interp = lambda A: np.column_stack([np.interp(idx, np.arange(n_fine), A[:, k]) for k in range(3)])
            T_new = interp(T)
            return interp(P), T_new / np.linalg.norm(T_new, axis=1)[:, None]
        P1, T1 = resample(P_loop, T_loop, loop_length)
        P2, T2 = resample(P_cork, T_cork, cork_length)
        P = np.vstack([P1, P2[1:]]) * scale
        T = np.vstack([T1, T2[1:]])

        # Up vectors. Half loop: the inward normal of the loop (upside-down at the top).
        # Half corkscrew: carried along without twisting, plus a smooth roll so it is upright at the neck.
        n1 = len(P1)
        N = np.zeros_like(P)
        N[:n1] = np.column_stack((-T[:n1, 1], T[:n1, 0], np.zeros(n1)))
        N[n1 - 1:] = _carry_normal(P[n1 - 1:], T[n1 - 1:], N[n1 - 1])
        want = np.array([0.0, 1.0, 0.0]) - T[-1, 1] * T[-1]
        want /= np.linalg.norm(want)
        roll = np.arctan2(np.cross(N[-1], want) @ T[-1], N[-1] @ want)
        w = np.linspace(0, 1, len(P) - n1 + 1)[1:]
        N[n1:] = _rotate_about(N[n1:], T[n1:], roll * (3 * w**2 - 2 * w**3))

        # Second half: mirror about the neck (z -> 2 * z_neck - z) and run backwards.
        # Up vectors are mirrored too (only their z flips; "up" is not reversed with the direction).
        z_neck = P[-1, 2]
        P_back = P[::-1].copy()
        P_back[:, 2] = 2 * z_neck - P_back[:, 2]
        N_back = N[::-1].copy()
        N_back[:, 2] *= -1

        X = np.concatenate([P[:, 0], P_back[1:, 0]])
        Y = np.concatenate([P[:, 1], P_back[1:, 1]])
        Z = np.concatenate([P[:, 2], P_back[1:, 2]])
        Nx = np.concatenate([N[:, 0], N_back[1:, 0]])
        Ny = np.concatenate([N[:, 1], N_back[1:, 1]])
        Nz = np.concatenate([N[:, 2], N_back[1:, 2]])
        return _build("cobrarollCG", h, X, Y, Z, Nx, Ny, Nz)

    # Helix track part (h = height; helix radius = 2h, 1.5 turns)
    #   1. Level, unbanked straight in (along +X), climbing smoothly from 0 to h
    #   2. Spiral of 1.5 turns, descending smoothly from h to 0. The curve tightens gradually over the
    #      first 45 degrees and loosens over the last 45 (curvature changes linearly: a clothoid),
    #      and the banking (45 deg at the top -> 63.4 deg at the bottom) rolls in and out with it.
    #   3. Level, unbanked straight out (along -X) back to X = 0
    # Points are evenly spaced (~0.5 m) along the track.
    @staticmethod
    def helix_func(h):
        R = 2 * h                       # helix radius
        total_turn = 3 * np.pi          # 1.5 turns: heading +X -> -X
        ease = np.radians(45.0)         # angle used to tighten into / loosen out of the circle
        step = 0.5                      # point spacing (m)

        # Spiral: curvature rises 0 -> 1/R over ease_length, stays 1/R, then falls back to 0
        ease_length = 2 * R * ease      # a linear curvature ramp turns through ease over this length
        circle_length = R * (total_turn - 2 * ease)
        turn_length = 2 * ease_length + circle_length
        n_turn = max(int(np.ceil(turn_length / step)), 100)
        s = np.linspace(0, turn_length, n_turn + 1)
        curvature = np.where(s < ease_length, s / ease_length,
                             np.where(s > turn_length - ease_length, (turn_length - s) / ease_length, 1.0)) / R
        ds = np.diff(s)
        heading = np.r_[0, np.cumsum(0.5 * (curvature[1:] + curvature[:-1]) * ds)]
        x_turn = np.r_[0, np.cumsum(0.5 * (np.cos(heading[1:]) + np.cos(heading[:-1])) * ds)]
        z_turn = -np.r_[0, np.cumsum(0.5 * (np.sin(heading[1:]) + np.sin(heading[:-1])) * ds)]

        # 1. Entry straight (3R long): climbs 0 -> h with no sudden change in slope
        entry_length = 3 * R
        n_entry = max(int(np.ceil(entry_length / step)), 10)
        X1 = np.linspace(0, entry_length, n_entry + 1)
        Y1 = h * _smootherstep(X1 / entry_length)

        # 2. Spiral: descends h -> 0; banking 45 -> 63.4 degrees, scaled in / out with the curvature
        u = s / turn_length
        X2 = entry_length + x_turn
        Y2 = h * (1 - _smootherstep(u))
        Z2 = z_turn
        Phi2 = (54.2 - 9.2 * np.cos(np.pi * u)) * (curvature * R)

        # 3. Exit straight: level and unbanked, back to X = 0
        n_exit = max(int(np.ceil(X2[-1] / step)), 2)
        X3 = np.linspace(X2[-1], 0, n_exit + 1)

        X = np.concatenate([X1, X2[1:], X3[1:]])
        Y = np.concatenate([Y1, Y2[1:], np.zeros(n_exit)])
        Z = np.concatenate([np.zeros(n_entry + 1), Z2[1:], np.full(n_exit, Z2[-1])])
        Phi = np.concatenate([np.zeros(n_entry + 1), Phi2[1:], np.zeros(n_exit)])

        Nx, Ny, Nz = _banked_normals(X, Y, Z, Phi)
        return _build("helix", h, X, Y, Z, Nx, Ny, Nz)

    # Horseshoe roll track part (done)
    # h = height of the horseshoe; the turn is 2h wide (same footprint as before)
    #   1. Level, unbanked straight in (along +X)
    #   2. 180 degree turn: it tightens and loosens gradually, climbs to h and drops back
    #      (highest at the tightest point, where the train is slowest), banking rolls in and out with it
    #   3. Level, unbanked straight back out (along -X), ending 2h to the side of the start
    # Points are evenly spaced (~0.5 m) along the track.
    @staticmethod
    def horseshoe_func(h):
        R = h                       # half the width of the turn
        bank_max = 63.4             # banking at the middle of the turn (degrees)
        straight = max(R, 5.0)      # length of each straight
        step = 0.5                  # point spacing (m)

        # Shape of the turn: heading goes 0 -> 180 degrees, turning slowly at the ends and fastest
        # in the middle (the curvature rises and falls smoothly, so there's no sudden jolt sideways)
        u_fine = np.linspace(0, 1, 4001)
        heading = np.pi * (u_fine - np.sin(2 * np.pi * u_fine) / (2 * np.pi))
        du = np.diff(u_fine)
        x_fine = np.r_[0, np.cumsum(0.5 * (np.cos(heading[1:]) + np.cos(heading[:-1])) * du)]
        z_fine = -np.r_[0, np.cumsum(0.5 * (np.sin(heading[1:]) + np.sin(heading[:-1])) * du)]
        turn_length = 2 * R / -z_fine[-1]   # makes the turn exactly 2R wide

        n_turn = max(int(np.ceil(turn_length / step)), 60)
        u = np.linspace(0, 1, n_turn + 1)
        X2 = straight + turn_length * np.interp(u, u_fine, x_fine)
        Z2 = turn_length * np.interp(u, u_fine, z_fine)
        Y2 = h * np.sin(np.pi * u) ** 4                                # level at both ends, top = h in the middle
        Phi2 = bank_max * (1 - np.cos(2 * np.pi * u)) / 2              # follows the curvature: 0 at the ends

        # Straights (level, no banking)
        n_straight = max(int(np.ceil(straight / step)), 2)
        X1 = np.linspace(0, straight, n_straight + 1)

        X = np.concatenate([X1, X2[1:], X1[::-1][1:]])
        Y = np.concatenate([np.zeros(len(X1)), Y2[1:], np.zeros(n_straight)])
        Z = np.concatenate([np.zeros(len(X1)), Z2[1:], np.full(n_straight, Z2[-1])])
        Phi = np.concatenate([np.zeros(len(X1)), Phi2[1:], np.zeros(n_straight)])

        Nx, Ny, Nz = _banked_normals(X, Y, Z, Phi)
        return _build("horseshoe", h, X, Y, Z, Nx, Ny, Nz)


    # =======================================================================
    #                               End Tracks
    # =======================================================================
    # Break track part (done)
    # this for a strong break A = 1.5g
    @staticmethod
    def brake_func(L):
        X = np.arange(0, L+1, 1)
        pts = len(X)

        Y, Z = np.zeros(pts), np.zeros(pts)
        # Straight along +X: the front (direction) vector is (1, 0, 0) at every point
        # (it used to be the X positions, which made the radius calculation see a fake 0.64 m bend)
        Fx, Fy, Fz = np.ones(pts), np.zeros(pts), np.zeros(pts)
        Lx, Ly, Lz = np.zeros(pts), np.zeros(pts), -np.ones(pts)
        Nx, Ny, Nz = np.zeros(pts), np.ones(pts), np.zeros(pts)
        return _finish("break", L, X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz)

    # Rollup track part (done)
    @staticmethod
    def rollup_func(h):
        R = (2 / 3) * h

        tan_60 = np.tan(np.radians(60))
        sin_60 = np.sin(np.radians(60))

        end_X1 = R * sin_60

        X1 = np.arange(0, end_X1, 1)
        Y1 = R - np.sqrt(R**2 - X1**2)
        Y1_end = R - np.sqrt(R**2 - end_X1**2)

        end_X2 = (2 * h) / (3 * tan_60) + end_X1
        X2 = np.arange(end_X1, end_X2, 1)
        Y2 = Y1_end + tan_60 * (X2 - end_X1)

        X = np.concatenate([X1, X2])
        Y = np.concatenate([Y1, Y2])
        Z = np.zeros(len(X))

        Nx, Ny, Nz = _planar_normals(X, Y)
        return _build("rollup", h, X, Y, Z, Nx, Ny, Nz)



    # =======================================================================
    #               Combine Multiple Track Parts into One
    # =======================================================================
    # Calculate XY Composition
    @staticmethod
    def calculate_xy_composition(parts, X, Y, Z):
        # === Calculates the xy VS z composition of the track ===
        xy_composition = []
        current_idx = 0
        for part in parts:
            part_section = part["section"]
            part_type = part["type"]

            seg_len = part["arrays"][0].size
            end_idx = current_idx + seg_len

            seg_X = X[current_idx:end_idx]
            seg_Z = Y[current_idx:end_idx]
            seg_Y = Z[current_idx:end_idx]

            dx = np.diff(seg_X, prepend=seg_X[0])
            dy = np.diff(seg_Y, prepend=seg_Y[0])

            if part_type != "Loop":
                distances_XY = np.sqrt(dx**2 + dy**2)
                part_XY = np.cumsum(distances_XY)
            else:
                heading_x = seg_X[-1] - seg_X[0]
                heading_y = seg_Y[-1] - seg_Y[0]
                heading_length = np.sqrt(heading_x**2 + heading_y**2)
                if heading_length > 1e-5:
                    ux = heading_x / heading_length
                    uy = heading_y / heading_length
                    part_XY = (seg_X - seg_X[0]) * ux + (seg_Y - seg_Y[0]) * uy
                else:
                    part_XY = seg_X - seg_X[0]

            xy_composition.append({
                "section": part_section, "type": part_type,
                "XY": part_XY, "Z": seg_Z
            })
            current_idx = end_idx

        return xy_composition

    # Combine multiple track parts into one (Done)
    @staticmethod
    # losses: None = frictionless (default), or physics.make_losses(...) for friction / air resistance
    def combine_tracks(*parts, section_folder ,coaster_name, write=True, losses=None):
        # Parts include the following:
        # "section": the section of the track part (Starts, Thrills 1, Turns, Thrills 2, Ends)
        # "type": the type of the track part
        # "arrays": the arrays of the track part (X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz, file_name)
        # "v_exit": the exit velocity of the track part (if applicable)
        if not parts:
            return None

        track_data = section_checks.initialize_track_data(parts)

        # === Combine the tracks together ===
        # Each piece is the 12 arrays (X, Y, Z, Fx, ..., Nz) of one part, already moved into place.
        # Initial track (Starting Track)
        pieces = [[arr.ravel().astype(float) for arr in parts[0]["arrays"][:12]]]
        # Get the velocity exiting from the starting track
        start_section = parts[0]["section"]
        v_exit = section_checks.start_exit_speed(parts[0]["type"], parts[0]["arrays"], parts[0]["v_exit"], losses)
        track_data[start_section]["stats"]["velocity_exit"] = v_exit


        # Goes through Thrills 1, Turns, Thrill 2, and Ends
        for part in parts[1:]:
            section_name = part["section"]
            section_type = part["type"]

            # === Physics checks for this section (see section_checks.py) ===
            # Done before the part is flipped/moved, using the speed it enters with
            stats, checks, v_exit = section_checks.analyze_section(section_name, section_type, part["arrays"], v_exit, losses)
            track_data[section_name]["stats"] = stats
            track_data[section_name]["checks"] = checks

            # Get the next parts data
            X2, Y2, Z2, Fx2, Fy2, Fz2, Lx2, Ly2, Lz2, Nx2, Ny2, Nz2 = [arr.ravel().astype(float) for arr in part["arrays"][:12]]

            # === After Turns Section Invert Track ===
            if section_name in INVERT_TRACKS:
                # If the part is a "Thrills 2" or "Ends" section, reverse the order of the arrays to ensure smooth connection
                if section_type == "Rollup":
                    X2, Y2, Z2 = -X2, Y2, Z2
                    Fx2, Fy2, Fz2 = -Fx2, Fy2, Fz2
                    Lx2, Ly2, Lz2 = -Lx2, Ly2, Lz2
                    Nx2, Ny2, Nz2 = -Nx2, Ny2, Nz2
                else:
                    X2, Y2, Z2 = X2[::-1], Y2, Z2[::-1]
                    Fx2, Fy2, Fz2 = -Fx2[::-1], -Fy2[::-1], -Fz2[::-1]
                    Lx2, Ly2, Lz2 = -Lx2[::-1], -Ly2[::-1], -Lz2[::-1]
                    Nx2, Ny2, Nz2 = Nx2[::-1], Ny2[::-1], Nz2[::-1]

            # Offset the new part to connect smoothly to the end of the previous part
            X_prev, Y_prev, Z_prev = pieces[-1][:3]
            X2 += X_prev[-1] - X2[0]
            Y2 += Y_prev[-1] - Y2[0]
            Z2 += Z_prev[-1] - Z2[0]

            pieces.append([X2, Y2, Z2, Fx2, Fy2, Fz2, Lx2, Ly2, Lz2, Nx2, Ny2, Nz2])

        # Concatenate all track parts at once
        X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz = [np.concatenate(column) for column in zip(*pieces)]

        # === Check to loop back to the start or not ===
        if not (parts[0]["type"] == "Rollback" or parts[-1]["type"] == "Rollup"):
            temp = X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz
            X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz = TrackPart.add_loop_back(temp)

        # === Combine all the data into a single array and write to file_utils ===
        # write=False skips the file (used by the web frontend's live preview)
        if write:
            pts = len(X)
            data = np.column_stack((np.arange(1, pts+1), X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz))
            file_utils.csv_noLimits_format(data, pts, 0, f"{section_folder}/Coasters/{coaster_name}")

        # === Data for SolidWorks ===
        # Clean up the data so that its viable to be used by SolidWorks for 3D printing
        # sw_data = np.column_stack((X, Y, Z))
        # matrix_diff = np.diff(sw_data, axis=0)
        # is_different = np.any(np.abs(matrix_diff) > 1e-5, axis=1)
        # cleaned_sw_data = np.vstack([sw_data[0], sw_data[1:][is_different]])
        # np.savetxt("to_solidwork.txt", cleaned_sw_data, fmt="%e", delimiter="\t")

        # Calculate XY vs Z Composition
        xy_composition = TrackPart.calculate_xy_composition(parts, X, Y, Z)

        # Create a dictionary to store the combined track data and the XY composition of each track part
        combined_track = (X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz, coaster_name)
        return combined_track, xy_composition, track_data

    # =======================================================================
    #           Loops the end back to the beginning of the track
    # =======================================================================
    @staticmethod
    def add_loop_back(combined_track):
        X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz = combined_track

        # Start and end
        x_start, y_start, z_start = X[0], Y[0], Z[0]
        x_end, y_end, z_end = X[-1], Y[-1], Z[-1]

        station_length = 5
        n_straight = 30
        n_arc = 80

        total_connector_points = n_straight + n_arc + n_straight

        Yc = np.linspace(y_end, y_start, total_connector_points)

        # Extend farther in negative X direction before turning
        x_ext = min(x_end, x_start) - station_length

        # Straight extension from track end
        x_a = np.linspace(x_end, x_ext, n_straight)
        z_a = np.full_like(x_a, z_end)

        # Semicircle in X-Z floor plane
        z_mid = (z_start + z_end) / 2
        radius = abs(z_start - z_end) / 2

        theta = np.linspace(0, np.pi, n_arc)

        # Flip this sign if the curve bends the wrong way
        bulge_sign = -1

        x_b = x_ext + bulge_sign * radius * np.sin(theta)
        z_b = z_mid + (z_end -  z_mid) * np.cos(theta)

        # Straight segment back to station/start
        x_c = np.linspace(x_ext, x_start, n_straight)
        z_c = np.full_like(x_c, z_start)

        Xc = np.concatenate([x_a, x_b, x_c])
        Zc = np.concatenate([z_a, z_b, z_c])

        # Simple connector vectors
        Fxc = np.diff(Xc, append=Xc[-1])
        Fyc = np.diff(Yc, append=Yc[-1])
        Fzc = np.diff(Zc, append=Zc[-1])

        Lxc = np.zeros_like(Xc)
        Lyc = np.zeros_like(Xc)
        Lzc = -np.ones_like(Xc)

        Nxc = np.zeros_like(Xc)
        Nyc = np.ones_like(Xc)
        Nzc = np.zeros_like(Xc)

        combined_track = (
            np.concatenate([X, Xc]),
            np.concatenate([Y, Yc]),
            np.concatenate([Z, Zc]),
            np.concatenate([Fx, Fxc]),
            np.concatenate([Fy, Fyc]),
            np.concatenate([Fz, Fzc]),
            np.concatenate([Lx, Lxc]),
            np.concatenate([Ly, Lyc]),
            np.concatenate([Lz, Lzc]),
            np.concatenate([Nx, Nxc]),
            np.concatenate([Ny, Nyc]),
            np.concatenate([Nz, Nzc]),
        )

        return combined_track


if __name__ == "__main__":
    (X, Y, Z, Fx, Fy, Fz, Lx, Ly, Lz, Nx, Ny, Nz, file_name) = TrackPart.corkscrew_func(20.0)

    # print(f"X: {max(X)}")
    # print(f"Y: {max(Y)}")

    # X, Y, Z = X[::-1], Y, Z[::-1]
    # Fx, Fy, Fz = -Fx[::-1], -Fy[::-1], -Fz[::-1]
    # Lx, Ly, Lz = -Lx[::-1], -Ly[::-1], -Lz[::-1]
    # Nx, Ny, Nz = Nx[::-1], Ny, Nz[::-1]


    # plt.figure()
    # plt.plot(X, Y, 'b-', label='Track Path')
    # plt.plot(X + Nx, Y + Ny, 'r-', alpha=0.4, label='Normals')
    # plt.plot(X, Z, 'b-', label='Track Path')
    # plt.plot(X + Nx, Z + Nz, 'r-', alpha=0.4, label='Normals')
    # plt.show()

    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.plot(X, Y, Z, 'b-', label='Track Path')
    ax.plot(X + Nx, Y + Ny, Z + Nz, 'r-', alpha=0.4, label='Normals')
    ax.set_aspect('equal', adjustable='box')
    plt.show()
