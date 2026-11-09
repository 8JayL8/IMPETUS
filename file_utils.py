import os
import shutil
import matplotlib.pyplot as plt
import numpy as np
import csv
import threading
from contextlib import contextmanager
from functools import lru_cache

# Folder write_csv saves track parts into, set by initalize_folders(). Kept per thread, so the
# web server can build several tracks at once without one request's folder leaking into another.
_local = threading.local()


def _get_segments_dir():
    return getattr(_local, "segments_dir", None)


def set_segments_dir(path):
    _local.segments_dir = path


# Temporarily stop write_csv from saving segments (used for test builds, e.g. recommendations)
@contextmanager
def no_segment_writes():
    saved = _get_segments_dir()
    set_segments_dir(None)
    try:
        yield
    finally:
        set_segments_dir(saved)


# Finds the absolute path of a section folder (inside the IMPETUS folder)
def get_section_path(section_folder):
    current_dir = os.path.dirname(os.path.abspath(__file__))

    cwd = os.getcwd()
    if os.path.basename(cwd) == "IMPETUS":
        base_dir = cwd
    else:
        base_dir = current_dir
        while os.path.basename(base_dir) != "IMPETUS" and os.path.dirname(base_dir) != base_dir:
            base_dir = os.path.dirname(base_dir)

        if os.path.basename(base_dir) != "IMPETUS":
            base_dir = cwd

    return os.path.join(base_dir, section_folder)


# True if this section already has a coaster with this name
def build_exists(section_folder, coaster_name):
    coaster_file = os.path.join(get_section_path(section_folder), "Coasters", f"{coaster_name}_0.csv")
    return os.path.isfile(coaster_file)


# Deletes a file or folder, printing (not crashing) if it can't be removed
def _remove(path):
    try:
        if os.path.isfile(path) or os.path.islink(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
    except Exception as e:
        print(f"Failed to delete {path}. Reason: {e}")


# Folder creation. Each coaster in a section gets its own files:
#   <section>/Coasters/<coaster>_0.csv
#   <section>/Images/<coaster>/...
#   <section>/Segments/<coaster>/...
# Only THIS coaster's old files are cleared, so other coasters in the same section are kept.
# Returns a dict of the folders: "master", "coaster", "images", "segments"
def initalize_folders(section_folder, coaster_name):
    master_folder = get_section_path(section_folder)

    folders = {
        "master": master_folder,
        "coaster": os.path.join(master_folder, "Coasters"),
        "images": os.path.join(master_folder, "Images", coaster_name),
        "segments": os.path.join(master_folder, "Segments", coaster_name),
    }

    # Clear the previous build of this coaster only
    _remove(folders["images"])
    _remove(folders["segments"])
    _remove(os.path.join(folders["coaster"], f"{coaster_name}_0.csv"))

    for folder in folders.values():
        os.makedirs(folder, exist_ok=True)

    set_segments_dir(folders["segments"])
    return folders


# All functions HERE has to do with file manipulation.
# ========================================================================
#                           Read from .csv files
# ========================================================================
# Each prebuilt file is read from disk only once (the recommendations build the same
# track many times). Callers get their own copy, so changing it can't change the cache.
def read_csv(file_name):
    data = _read_csv_cached(file_name)
    return None if data is None else data.copy()


@lru_cache(maxsize=None)
def _read_csv_cached(file_name):
    all_data = []
    try:
        with open(f"Prebuilt_tracks/{file_name}", "r", newline="", encoding="utf-8") as csvfile:
            # Peek at the first line to detect the delimiter
            first_line = csvfile.readline()
            if not first_line.strip(): 
                print(f"Error: No data found in file '{file_name}'.")
                return None
            
            # Reset file pointer back to the beginning
            csvfile.seek(0) 
            
            # Dynamically choose parser based on whether a comma is present
            if ',' in first_line:
                reader = csv.reader(csvfile, delimiter=',')
            else:
                # Custom generator to handle arbitrary spaces/tabs smoothly
                reader = (line.split() for line in csvfile)
            
            # Skip Header
            next(reader) 
            
            # Read each row
            for row in reader: 
                if not row:  # Skip empty rows
                    continue
                try: 
                    # Convert values to float (stripping quotes just in case)
                    all_data.append([float(v.strip('"\'')) for v in row])
                except ValueError as e:
                    print(f"Warning: Could not convert row {row} ({e})")

    except FileNotFoundError:
        print(f"Error: File '{file_name}' not found.")
        return None
    except Exception as e:
        print(f"Error reading file: {e}")
        return None

    data = np.array(all_data)
    data.setflags(write=False)   # the cached array must never be changed
    return data


# ========================================================================
#                           Write to .csv files
# ========================================================================
# Gets the data, points, track properties (length, height, radius), and track name and convert it into a csv
def write_csv(data, pts, prop, elementname):
    # Make the filename for CSV (function_Length_Index)
    segments_dir = _get_segments_dir()
    if segments_dir is None:
        return None   # no section folder yet (e.g. running tracks.py on its own)
    file_name = os.path.join(segments_dir, f"{elementname}_{prop}.csv")
    # Open the file and write the following into it
    with open(file_name, mode="w", newline="") as f:
        writer = csv.writer(f)
        header = ['"No."','"PosX"','"PosY"','"PosZ"','"FrontX"','"FrontY"','"FrontZ"','"LeftX"','"LeftY"','"LeftZ"','"UpX"','"UpY"','"UpZ"']
        writer.writerow(header)
        writer.writerows(data)

    return None


# ========================================================================
#                           Generate .svg files
# ========================================================================
def export_layouts(images_folder, track_data, xy_composition, track_plots):
    X, Y, Z, *unused_data = track_data
    font_size, cushion = 8, 5

    x_min_top, x_max_top = np.min(X), np.max(X)
    z_min_top, z_max_top = np.min(Z), np.max(Z)
    top_view_y_span = z_max_top - z_min_top

    # Used to find the boundaries of each segment
    segment_boundaries = calculate_segment_boundaries(xy_composition)

    # Build the combined subplots matrix
    fig, axes = plt.subplots(4, 1, figsize=(24, 48))
    combined_configs = [
        {"title": "Whole Track Top View", "type": "top"},
        {"title": "Section 1-2",           "type": "sec_12"},
        {"title": "Section 3",             "type": "sec_3"},
        {"title": "Section 4-5",           "type": "sec_45"}
    ]
    
    # Exports a
    combined_view(axes, combined_configs, xy_composition, segment_boundaries, X, Z)

    # 3. Export standalone views with temporary context decorations
    export_individual_views(images_folder, track_plots, segment_boundaries, font_size)

    # 4. Format combined axes, split if necessary, and save print layout components
    export_printed_pieces(images_folder, axes, combined_configs, xy_composition, X, Z, cushion, top_view_y_span, x_min_top, x_max_top, z_min_top, z_max_top)

    # Final combined save
    fig.subplots_adjust(left=1.0/24.0, right=1.0-(1.0/24.0), bottom=1.0/12.0, top=1.0-(1.0/12.0))
    fig.savefig(f"{images_folder}/combined_track_views.svg", dpi=300)
    plt.close(fig)


# === Finds the segment boundaries
def calculate_segment_boundaries(xy_composition):
    segment_boundaries = {}
    current_horizontal_offset = 0
    
    # Find the start and end of each track segment
    for idx, segment in enumerate(xy_composition):
        local_horizontal = segment["XY"]
        global_2d_horizontal = local_horizontal + current_horizontal_offset
        segment_boundaries[idx] = {
            "start_x": global_2d_horizontal[0],
            "end_x": global_2d_horizontal[-1],
        }
        current_horizontal_offset = global_2d_horizontal[-1]
    return segment_boundaries

# === Display the top view and all sideview compoenents to scale with the top view ===
def combined_view(axes, combined_configs, xy_composition, segment_boundaries, X, Z):
    section_colors = {
        "sec_1": "#1f77b4",
        "sec_2": "#ff7f0e",
        "sec_3": "#2ca02c", 
        "sec_4": "#c13017",
        "sec_5": "#1725c1"
    }
    
    axes[0].plot(0, 0, color='black', marker='o', markersize=6, zorder=5)
    current_horizontal_offset = 0
    array_idx_start = 0

    for idx, segment in enumerate(xy_composition):
        local_horizontal = segment["XY"]
        Z_elevation = segment["Z"]
        global_2d_horizontal = local_horizontal + current_horizontal_offset
        segment_color = section_colors.get(f"sec_{idx+1}", "gray")
        array_idx_end = array_idx_start + len(local_horizontal)
        
        # Plot top view
        axes[0].plot(X[array_idx_start:array_idx_end], Z[array_idx_start:array_idx_end], color=segment_color, linewidth=2)
        if idx < len(xy_composition) - 1:
            transition_idx = min(array_idx_end - 1, len(X) - 1)
            axes[0].plot(X[transition_idx], Z[transition_idx], color='black', marker='o', markersize=6, zorder=5)

        # Plot side views
        for ax_idx, config in enumerate(combined_configs[1:], start=1):
            plot_type = config["type"]
            is_in_this_row = (
                (plot_type == "sec_12" and idx in (0, 1)) or
                (plot_type == "sec_3"  and idx == 2) or
                (plot_type == "sec_45" and idx in (3, 4))
            )
            if is_in_this_row:
                row_start_offset = (segment_boundaries[0]["start_x"] if idx in (0, 1) else 
                                    segment_boundaries[2]["start_x"] if idx == 2 else 
                                    segment_boundaries[3]["start_x"])
                axes[ax_idx].plot(global_2d_horizontal - row_start_offset, Z_elevation, color=segment_color, linewidth=2)

        array_idx_start = array_idx_end - 1
        current_horizontal_offset = global_2d_horizontal[-1]


def export_individual_views(images_folder, track_plots, segment_boundaries, font_size):
    """Decorates, saves, and reverts isolated view plots from track_plots dict."""
    view_configs = [
        ("whole_track_topview",  "Whole Track Topview"),
        ("whole_track_sideview", "Whole Track Sideview"),
        ("section_12",           "Section 1-2"),
        ("section_3",            "Section 3"),
        ("section_45",           "Section 4-5")
    ]

    for key, title in view_configs:
        if key not in track_plots:
            continue
            
        ax = track_plots[key]["ax"]
        filename = f"{title.lower().replace(' ', '_')}.svg"
        temp_elements = []
        y_min, y_max = ax.get_ylim()   # restored after saving (the sideview changes it)

        # If its the whole track sideview, plot with guidelines below the track
        if key == "whole_track_sideview":
            padding = (y_max - y_min) * 0.8
            new_y_min = y_min - padding
            ax.set_ylim(bottom=new_y_min)

            canvas_floor_y = new_y_min
            upper_hline_y = new_y_min + (padding * 0.85)
            lower_hline_y = new_y_min + (padding * 0.35)
            label_y = new_y_min + (padding * 0.60)

            global_start_x = segment_boundaries[0]["start_x"]
            global_end_x = segment_boundaries[max(segment_boundaries.keys())]["end_x"]

            temp_elements.append(ax.plot([global_start_x, global_end_x], [upper_hline_y, upper_hline_y], color='red', linestyle='-', linewidth=0.6, zorder=1)[0])
            temp_elements.append(ax.plot([global_start_x, global_end_x], [lower_hline_y, lower_hline_y], color='blue', linestyle='-', linewidth=0.6, zorder=1)[0])
            temp_elements.append(ax.plot([global_start_x, global_start_x], [canvas_floor_y, upper_hline_y], color='gray', linestyle='-', linewidth=0.6, zorder=1)[0])
            temp_elements.append(ax.plot([global_end_x, global_end_x], [canvas_floor_y, upper_hline_y], color='gray', linestyle='-', linewidth=0.6, zorder=1)[0])

            for s_idx, bounds in segment_boundaries.items():
                mid_x_loc = (bounds["start_x"] + bounds["end_x"]) / 2.0
                section_name = ax.text(x=mid_x_loc, y=label_y, s=f"Section {s_idx+1}", fontsize=font_size * 0.6, color='black', ha='center', va='center')
                temp_elements.append(section_name)

                if s_idx < len(segment_boundaries) - 1:
                    sub_vline, = ax.plot([bounds["end_x"], bounds["end_x"]], [canvas_floor_y, lower_hline_y], color='gray', linestyle='-', linewidth=0.6, zorder=2)
                    temp_elements.append(sub_vline)

        ax.axis('off')
        ax.set_title(title, fontsize=font_size)
        ax.figure.savefig(f"{images_folder}/{filename}", dpi=300)
        ax.axis('on')

        # Clean up temporary layout lines
        for element in temp_elements:
            element.remove()
        if key == "whole_track_sideview":
            ax.set_ylim(y_min, y_max)


# Builds the greek key (square wave) along the bottom of a printed piece:
#   gap, tooth, gap, tooth, ...   each gap/tooth is `step` wide and `tooth_height` tall.
# The length is rounded UP to whole steps so every tooth is full size (0.5 in).
# The key starts AND ends on the baseline, so the bound lines connect to it.
# Returns (xs, ys, x_end) where x_end is where the right bound line goes.
def _greek_key(x_start, x_end, y_base, step, tooth_height):
    n_steps = max(1, int(np.ceil((x_end - x_start) / step - 1e-9)))
    x_end = x_start + n_steps * step
    y_top = y_base + tooth_height

    xs, ys = [x_start], [y_base]
    for i in range(n_steps):
        x0, x1 = x_start + i * step, x_start + (i + 1) * step
        if i % 2 == 1:   # tooth: up, across, down
            xs += [x0, x1, x1]
            ys += [y_top, y_top, y_base]
        else:            # gap: along the baseline
            xs.append(x1)
            ys.append(y_base)
    return xs, ys, x_end


# Copies a line from the combined view onto a printed piece.
# If lo/hi are given, only the part of the line inside [lo, hi] is copied (moved left by `shift`),
# drawn as separate runs so a cut line never gets joined across a gap.
def _copy_line(ax, line, lo=None, hi=None, shift=0.0):
    lx = np.asarray(line.get_xdata(), dtype=float)
    ly = np.asarray(line.get_ydata(), dtype=float)
    style = dict(color=line.get_color(), linewidth=line.get_linewidth(), linestyle=line.get_linestyle(),
                 marker=line.get_marker(), markersize=line.get_markersize())
    if lo is None:
        ax.plot(lx, ly, **style)
        return

    inside = (lx >= lo) & (lx <= hi)
    if not np.any(inside):
        return
    edges = np.flatnonzero(np.diff(inside.astype(int))) + 1
    for run in np.split(np.arange(len(lx)), edges):
        if inside[run[0]]:
            ax.plot(lx[run] - shift, ly[run], **style)


def export_printed_pieces(images_folder, axes, combined_configs, xy_composition, X, Z, cushion, top_view_y_span, x_min_top, x_max_top, z_min_top, z_max_top):
    """Processes scaling, adds tooth baselines, and cuts ultra-wide plots into printable chunks."""
    page_width_in, page_height_in = 24.0, 12.0    # Cricut mat size
    margin_in = 1.0                               # empty border around the drawing
    box_width_in = page_width_in - 2 * margin_in  # 22 in drawing area

    for ax_idx, config in enumerate(combined_configs):
        ax = axes[ax_idx]
        plot_type = config["type"]

        if plot_type == "top":
            ax.plot(x_min_top, 0, 'go', markersize=8)
            ax.plot(x_max_top, 0, 'go', markersize=8)
            ax.set_xlim(x_min_top - cushion, x_max_top + cushion)
            ax.set_ylim(z_min_top - cushion, z_max_top + cushion)
        else:
            lines = ax.get_lines()
            y_base = min([np.min(l.get_ydata()) for l in lines] + [np.max(l.get_ydata()) for l in lines]) if lines else 0
            ax.set_xlim(x_min_top - cushion, x_max_top + cushion)
            ax.set_ylim(y_base - cushion, y_base + top_view_y_span + cushion)

        ax.set_aspect('equal', adjustable='box')
        ax.axis('off')

        current_xlim = ax.get_xlim()
        track_x_data, track_y_data = [], []
        for line in ax.get_lines():
            track_x_data.extend(line.get_xdata())
            track_y_data.extend(line.get_ydata())
        track_x_data, track_y_data = np.array(track_x_data, dtype=float), np.array(track_y_data, dtype=float)

        # Every printed piece uses the same scale as the top view: 22 in = the top view's width
        box_data_width = float(current_xlim[1] - current_xlim[0])
        one_inch_in_data_units = box_data_width / box_width_in

        t_min_x = float(np.min(track_x_data)) if track_x_data.size > 0 else 0.0
        t_max_x = float(np.max(track_x_data)) if track_x_data.size > 0 else 1.0
        actual_track_span = t_max_x - t_min_x

        # Cut side views into as many equal pieces as needed to fit the page (leaving room for the key)
        if plot_type == "top":
            n_pieces = 1
        else:
            n_pieces = max(1, int(np.ceil(actual_track_span / (0.9 * box_data_width))))
        piece_length = actual_track_span / n_pieces

        # Greek key size and the vertical limits shared by all pieces of this view
        step_size = 0.5 * one_inch_in_data_units      # 0.5 in wide
        tooth_height = 0.5 * one_inch_in_data_units   # 0.5 in tall
        lowest_point = float(np.min(track_y_data)) if track_y_data.size > 0 else 0.0
        highest_point = float(np.max(track_y_data)) if track_y_data.size > 0 else 10.0
        y_baseline = lowest_point - (one_inch_in_data_units * 2.0)
        y_top_limit = highest_point + (one_inch_in_data_units * 1.5)

        for piece in range(n_pieces):
            piece_lo = t_min_x + piece * piece_length
            piece_hi = piece_lo + piece_length
            shift = piece_lo - t_min_x   # every piece is drawn starting at t_min_x

            if plot_type == "top":
                y_lo, y_hi = ax.get_ylim()
                data_min_x, data_max_x = t_min_x, t_max_x
            else:
                # Greek key along the bottom, ending exactly on the right bound line
                key_x, key_y, key_end_x = _greek_key(t_min_x, t_min_x + piece_length, y_baseline, step_size, tooth_height)
                y_lo, y_hi = y_baseline - (one_inch_in_data_units * 0.5), y_top_limit
                data_min_x, data_max_x = t_min_x, key_end_x

            # Page sized so the drawing is exactly to scale (normally the 24 x 12 in mat)
            content_height_in = (y_hi - y_lo) / one_inch_in_data_units
            box_height_in = max(page_height_in - 2 * margin_in, content_height_in)
            if content_height_in > page_height_in - 2 * margin_in:
                print(f"Note: {config['title']} is {content_height_in:.1f} in tall; page made taller than {page_height_in:.0f} in to stay to scale.")
            fig_height_in = box_height_in + 2 * margin_in

            single_fig = plt.figure(figsize=(page_width_in, fig_height_in))
            single_ax = single_fig.add_axes([margin_in / page_width_in, margin_in / fig_height_in,
                                             box_width_in / page_width_in, box_height_in / fig_height_in])

            for line in ax.get_lines():
                if n_pieces == 1:
                    _copy_line(single_ax, line)
                else:
                    _copy_line(single_ax, line, piece_lo, piece_hi, shift)

            if plot_type == "top":
                dot_array_idx = 0
                for segment in xy_composition[:-1]:
                    dot_array_idx += len(segment["XY"]) - 1
                    single_ax.plot(X[dot_array_idx], Z[dot_array_idx], color='black', marker='o', markersize=6, zorder=5)
            else:
                single_ax.plot(key_x, key_y, color='black', linewidth=1, zorder=1)
                # Vertical lines are the beginning and end (Used for Cricut)
                single_ax.plot([t_min_x, t_min_x], [y_baseline, y_top_limit], color='black', linewidth=1)
                single_ax.plot([key_end_x, key_end_x], [y_baseline, y_top_limit], color='black', linewidth=1)

            # Exact limits: 22 in across = box_data_width and the height matches the box,
            # so the drawing is never shrunk (1 in on paper = 1 in on the plan)
            data_mid_x = (data_min_x + data_max_x) / 2.0
            single_ax.set_xlim(data_mid_x - box_data_width / 2.0, data_mid_x + box_data_width / 2.0)
            extra_y = (box_height_in * one_inch_in_data_units - (y_hi - y_lo)) / 2.0
            single_ax.set_ylim(y_lo - extra_y, y_hi + extra_y)
            single_ax.axis('off')

            safe_title = config["title"].lower().replace(' ', '_').replace('-', '_')
            suffix = f"_piece_{chr(ord('A') + piece)}" if n_pieces > 1 else ""
            single_fig.savefig(f"{images_folder}/to_print_{safe_title}{suffix}.svg", dpi=300, transparent=True, facecolor='none', pad_inches=0)
            plt.close(single_fig)

# ========================================================================
#                       NoLimits 2 Spline Format
# ========================================================================
# Output format checked against NoLimits 2 -- re-test in NoLimits after any change.
def csv_noLimits_format(data, pts, prop, elementname):
    file_name = f"{elementname}_{prop}.csv"

    # NoLimits 2 spline header, tab separated
    header_line = '"No."\t"PosX"\t"PosY"\t"PosZ"\t"FrontX"\t"FrontY"\t"FrontZ"\t"LeftX"\t"LeftY"\t"LeftZ"\t"UpX"\t"UpY"\t"UpZ"'

    # Index as an integer, then the 12 coordinates/vectors in scientific notation (e.g. 1.234560e+01).
    # newline="" keeps plain \n line endings on Windows too.
    with open(file_name, mode="w", newline="", encoding="utf-8") as f:
        np.savetxt(f, data[:pts, :13], fmt=["%d"] + ["%e"] * 12, delimiter="\t",
                   header=header_line, comments="")

    print(f"file {file_name} created successfully")
    return None


if __name__ == "__main__":
    # initalize_folders("Test_Section_123")
    pass