import numpy as np
import file_utils
import section_checks   # All physics checks for each section (uses physics.py)
from physics import G   # gravity (m/s^2)
import matplotlib.pyplot as plt

INVERT_TRACKS = ["Thrills 2", "Ends"]   # Inverted tracks


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


# Reads a prebuilt track (from Prebuilt_tracks/), scales it so its max height is h,
# and stretches its X by x_stretch
def _load_prebuilt(csv_name, h, x_stretch, file_name):
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
        track_content = _load_prebuilt("cometlifthill.csv", h, 1, "lifthill")
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
        return _load_prebuilt("cometcamelback.csv", h, 1 / 3, "camelback")

    # Corkscrew track part (done)
    @staticmethod
    def corkscrew_func(h):
        H = h * 4 # Total height of corkscrew
        r1 = H / 2 # Radius of corkscrew
        B = 1 / (2 * r1)
        stretch_factor = 2 # Stretch factor for the corkscrew

        l2_base = ((3 * np.pi * np.sqrt(H - h)) / 2) * stretch_factor
        l1 = (-3 * h * np.pi / (2*l2_base) + np.sqrt((3 * h *np.pi / (2 * l2_base))**2 + 6 * B * h)) / (2 * B)
        A = h/(2*l1**3)-B/l1

        # Section 1 (Track before the loop)
        X1 = np.linspace(0, l1, 50)
        t_norm1 = X1 / l1
        smooth_modifier = (3 * t_norm1**2 - 2 * t_norm1**3)
        Y1 = ((A * X1**3) + (B * X1**2)) * smooth_modifier
        Z1 = np.zeros_like(X1)
        Phi1 = -90 * (0.5 - 0.5 * np.cos(np.pi * t_norm1))

        # Section 2 (Track for the loop of corkscrew)
        l2 = l2_base
        t = np.arange(0, 3 * np.pi, 0.01)
        X2 = l2 * t / (3 * np.pi) + X1[-1]
        Y2 = (h / 2) * (1 + np.sin(t)) # Responsible for the loop angle
        Z2 = (h / 2) * (1 - np.cos(t)) + Z1[-1] # Offset to the side, so that the track doesn't turn into itself
        Phi2 = -90 - (540 / (3 * np.pi))*t

        # Section 3 (Track after the loop)
        X3 = np.linspace(0, l1, len(X1)) + X2[-1]
        Y3 = np.flip(Y1)
        Z3 = Z2[-1] - np.flip(Z1)
        Phi3 = -np.flip(Phi1)

        # Combines the three sections into one
        X = np.concatenate([X1, X2, X3])
        Y = np.concatenate([Y1, Y2, Y3])
        Z = np.concatenate([Z1, Z2, Z3])
        Phi = np.concatenate([Phi1, Phi2, Phi3])

        Nx, Ny, Nz = _rotate_normals(X, Y, Z, Phi)
        return _build("corkscrew", r1, X, Y, Z, Nx, Ny, Nz)

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

        xx = np.arange(1, len(X)+1)
        Z = np.cos((np.pi / max(xx)) * xx) - 1 # Adjust Z offset to create the loop shape without colliding with itself

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
    # Cobra Roll track part (done)
    @staticmethod
    def cobrarollCG_func(h):
        return _load_prebuilt("flashbackcobraroll.csv", h, 3, "cobrarollCG")

    # Helix track part (done)
    @staticmethod
    def helix_func(h):
        R = 2 * h

        # All X components to the track
        X1 = np.arange(0, 3*R + 1, 1)
        X2 = np.arange(3*R + 1, 4*R + 1, 1)
        X3 = np.arange(4*R - 1, 2*R - 1, -1)
        X4 = np.arange(2*R + 1, 4*R + 1, 1)
        X5 = np.arange(4*R - 1, 3*R - 1, -1)
        X6 = np.arange(3*R - 1, -1, -1)

        # All Y components to the track
        Y1 = (h/2) * (1 - np.cos((np.pi*X1) / (3*R)))
        helix_steps = 6 * R
        Y2345 = np.max(Y1) - (h/2) * (1 - np.cos(np.pi * np.arange(1, helix_steps + 1, 1) / helix_steps))
        Y6 = np.zeros(len(X6))

        # All Z components to the track (points just outside the circle are put on it)
        def circle(Xs):
            return np.sqrt(np.clip(R**2 - (Xs - 3*R)**2, 0, None))
        Z1 = np.zeros(len(X1))
        Z2 = -R + circle(X2)
        Z3 = -R - circle(X3)
        Z4 = -R + circle(X4)
        Z5 = -R - circle(X5)
        Z6 = np.full(len(X6), -2*R)

        # All Phi components to the track (angle)
        Phi1 = (45/2) * (1 - np.cos((np.pi*X1) / (3*R)))
        Phi2345 = 54.2 + 9.2 * (-np.cos(np.pi * np.arange(1, helix_steps + 1, 1) / helix_steps))
        Phi6 = 63.4 + (63.4/2) * (-1 + np.cos(np.pi * X6 / (3*R)))

        # Combining compnents
        X = np.concatenate([X1, X2, X3, X4, X5, X6])
        Y = np.concatenate([Y1, Y2345, Y6])
        Z = np.concatenate([Z1, Z2, Z3, Z4, Z5, Z6])
        Phi = np.concatenate([Phi1, Phi2345, Phi6])

        Nx, Ny, Nz = _rotate_normals(X, Y, Z, Phi)
        return _build("helix", h, X, Y, Z, Nx, Ny, Nz)

    # Horseshoe roll track part (done)
    @staticmethod
    def horseshoe_func(h):
        R = h

        X1 = np.arange(0, R, 1)
        X2 = np.arange(R, 2 * R, 1)
        X3 = np.arange(2 * R, R, -1)
        X4 = np.arange(R, -1, -1)
        X = np.concatenate([X1, X2, X3, X4])
        pts = len(X)

        idx = np.arange(1, pts + 1)
        Y = (h / 2) * (1 - np.cos(2 * np.pi * idx / pts))

        Z1 = np.zeros(len(X1))
        Z2 = -R + np.sqrt(R**2 - (X2 - R)**2)
        Z3 = -R - np.sqrt(R**2 - (X3 - R)**2)
        Z4 = -2.0 * R * np.ones(len(X4))
        Z = np.concatenate([Z1, Z2, Z3, Z4])

        Phi1 = (63.4 / 2.0) * (1.0 - np.cos((np.pi / R) * X1))
        Phi2 = 63.4 * np.ones(len(X2))
        Phi3 = 63.4 * np.ones(len(X3))
        Phi4 = (63.4 / 2.0) * (1.0 - np.cos((np.pi / R) * X4))
        Phi = np.concatenate([Phi1, Phi2, Phi3, Phi4])

        Nx, Ny, Nz = _rotate_normals(X, Y, Z, Phi, forward_first=True)
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
        Fx, Fy, Fz = X.copy(), Y, Z
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
    def combine_tracks(*parts, section_folder ,coaster_name):
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
        v_exit = parts[0]["v_exit"]
        track_data[start_section]["stats"]["velocity_exit"] = v_exit


        # Goes through Thrills 1, Turns, Thrill 2, and Ends
        for part in parts[1:]:
            section_name = part["section"]
            section_type = part["type"]

            # === Physics checks for this section (see section_checks.py) ===
            # Done before the part is flipped/moved, using the speed it enters with
            stats, checks, v_exit = section_checks.analyze_section(section_name, section_type, part["arrays"], v_exit)
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
