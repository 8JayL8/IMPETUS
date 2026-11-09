// Page state shared by every module, plus helpers that read it.
import { SECTION_COLORS, CONNECTOR_COLOR } from "./constants.js";

export const state = {
  options: null,
  rows: {},          // section -> {type, value, els}
  lastResult: null,
  recs: null,
  // friction / air resistance (filled with the server's defaults when first turned on)
  physics: {
    friction: { enabled: false, mu: null },
    air: { enabled: false, cd: null, area: null, mass: null },
  },
};

export function currentTracks() {
  return state.options.sections.map((section) => ({
    section,
    type: state.rows[section].type || null,
    value: state.rows[section].value,
  }));
}

export function currentPhysics() {
  const { friction, air } = state.physics;
  return {
    friction: { enabled: friction.enabled, mu: friction.mu },
    air: { enabled: air.enabled, cd: air.cd, area: air.area, mass: air.mass },
  };
}

export function physicsKey() {
  const { friction, air } = state.physics;
  return `${friction.enabled ? friction.mu : "-"}|${air.enabled ? [air.cd, air.area, air.mass].join(",") : "-"}`;
}

export function lossesOn() {
  return state.physics.friction.enabled || state.physics.air.enabled;
}

// Slices of the combined track: one per section, then the return track (if any)
export function trackSlices(result) {
  const slices = [];
  let start = 0;
  for (const s of result.sections) {
    slices.push({ section: s.section, from: start, to: start + s.points, color: SECTION_COLORS[s.section] });
    start += s.points;
  }
  const total = result.track.X.length;
  if (start < total) slices.push({ section: "Return", from: start - 1, to: total, color: CONNECTOR_COLOR });
  return slices;
}

export function hasReturnTrack(result) {
  return trackSlices(result).some((s) => s.section === "Return");
}
