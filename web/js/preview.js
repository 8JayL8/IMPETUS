// Live preview and recommendations requests.
// Every slider change rebuilds the whole track on the server (~10 ms), because a section's
// exit speed changes the physics checks of every section after it.
import { api, setStatus } from "./api.js";
import { state, currentTracks, currentPhysics, physicsKey, lossesOn } from "./state.js";
import { updateRecommendationUI } from "./cards.js";
import { render } from "./render.js";

// ========================================================================
//    Live preview: at most one request in flight, always the latest
// ========================================================================
let inFlight = false;
let pending = false;

export function requestPreview() {
  if (inFlight) { pending = true; return; }
  inFlight = true;
  pending = false;
  const started = performance.now();

  api("/api/preview", { tracks: currentTracks(), physics: currentPhysics() })
    .then((result) => {
      state.lastResult = result;
      render(result);
      const ms = Math.round(performance.now() - started);
      const failed = result.sections.filter((s) => !s.passed).length;
      const losses = result.losses
        ? ` · ${[state.physics.friction.enabled && `friction μ ${state.physics.friction.mu}`,
                 state.physics.air.enabled && "air resistance"].filter(Boolean).join(" + ")}`
        : " · frictionless";
      setStatus(`${result.track.X.length} points · ${ms} ms round trip${losses} · ` +
        (failed ? `${failed} section(s) failing checks` : "all checks passed"), false);
    })
    .catch((err) => setStatus(err.message, true))
    .finally(() => {
      inFlight = false;
      if (pending) requestPreview();
    });
}

// ========================================================================
//                          Recommendations
// ========================================================================
// Recommendations depend on 'Starts' (and, with friction / air resistance on, on the tracks picked
// before each section, since they slow the train down). They take longer, so wait until the user pauses.
let recTimer = null;
const recCache = new Map();

function recKey() {
  const start = state.rows["Starts"];
  // Frictionless, the later picks don't change the recommendations, so they aren't part of the key
  const picks = lossesOn()
    ? currentTracks().filter((t) => t.section !== "Starts").map((t) => `${t.type || "-"}:${t.value}`).join(",")
    : "";
  return `${start.type}|${start.value}|${physicsKey()}|${picks}`;
}

export function scheduleRecommendations() {
  clearTimeout(recTimer);
  recTimer = setTimeout(async () => {
    const start = state.rows["Starts"];
    if (!start.type) return;
    const key = recKey();
    try {
      if (!recCache.has(key)) {
        recCache.set(key, await api("/api/recommendations",
          { start_type: start.type, start_value: start.value, physics: currentPhysics(), tracks: currentTracks() }));
      }
      // Ignore the answer if the inputs changed while waiting
      if (key === recKey()) {
        state.recs = recCache.get(key);
        updateRecommendationUI();
      }
    } catch (err) {
      console.warn("Recommendation failed:", err);
    }
  }, 200);
}

// A section's track type or value changed
export function tracksChanged(section) {
  requestPreview();
  if (section === "Starts" || lossesOn()) scheduleRecommendations();
}
