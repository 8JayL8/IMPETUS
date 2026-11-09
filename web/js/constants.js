// Shared constants: colours, starting layout, stat labels, rail sizes.

export const SECTION_COLORS = {
  "Starts": "#2563eb",
  "Thrills 1": "#ea580c",
  "Turns": "#7c3aed",
  "Thrills 2": "#0d9488",
  "Ends": "#db2777",
};
export const CONNECTOR_COLOR = "#9ca3af";   // the return track back to the station

// Start / end / direction markers (3D view and 2D views)
export const START_COLOR = "#16a34a";
export const END_COLOR = "#dc2626";
export const ARROW_COLOR = "#0f172a";

// Starting layout shown when the page opens
export const DEFAULTS = {
  "Starts": ["Lift Hill", 30],
  "Thrills 1": ["Loop", 23],
  "Turns": ["Helix", 15],
  "Thrills 2": ["Camelback", 27],
  "Ends": ["Brake", 20],
};

export const STAT_LABELS = {
  acceleration: ["Acceleration", "g"],
  velocity_exit: ["Exit speed", "m/s"],
  v_bottom: ["Speed at bottom", "m/s"],
  v_top: ["Speed at top", "m/s"],
  r_bottom: ["Radius at bottom", "m"],
  r_top: ["Radius at top", "m"],
  deg_banking: ["Banking", "°"],
  deg_top: ["Banking at top", "°"],
  deg_bottom: ["Banking at bottom (steepest)", "°"],
  // the forces the checks used, so they can be worked out by hand
  g_top: ["Force at top (v²/gr − 1)", "g"],
  g_min: ["Lowest seat force", "g"],
  g_valley: ["Valley force", "g"],
  valley_ny: ["Valley n_y", ""],
  g_lateral: ["Worst sideways force", "g"],
  v_lateral: ["Speed at worst sideways", "m/s"],
  r_lateral: ["Radius at worst sideways", "m"],
};

// Rails (3D track and the train's wheels)
export const RAIL_GAUGE = 1.0;          // metres between the two rails
export const RAIL_RADIUS = 0.07;
export const SPINE_DROP = 0.45;         // spine sits this far below the rails
export const SPINE_RADIUS = 0.16;
