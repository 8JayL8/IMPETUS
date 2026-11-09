// Physics panel: friction + air resistance toggles and inputs (off = frictionless).
import { state } from "./state.js";

const PHYSICS_FIELDS = {
  friction: { button: "friction-btn", fields: "friction-fields", reset: "friction-reset", inputs: { mu: "mu-input" } },
  air: { button: "air-btn", fields: "air-fields", reset: "air-reset",
         inputs: { cd: "cd-input", area: "area-input", mass: "mass-input" } },
};

// onChange() is called (debounced) whenever a setting changes
export function setupPhysicsPanel(onChange) {
  const defaults = state.options.physics_defaults;
  const limits = state.options.physics_limits;
  let timer = null;
  const changed = () => {
    updatePhysicsSummary();
    clearTimeout(timer);
    timer = setTimeout(onChange, 120);
  };

  for (const [group, cfg] of Object.entries(PHYSICS_FIELDS)) {
    const button = document.getElementById(cfg.button);
    const fields = document.getElementById(cfg.fields);
    const settings = state.physics[group];

    for (const [key, id] of Object.entries(cfg.inputs)) {
      const input = document.getElementById(id);
      [input.min, input.max] = limits[key];
      input.addEventListener("input", () => {
        const v = parseFloat(input.value);
        const [low, high] = limits[key];
        input.classList.toggle("invalid", !(Number.isFinite(v) && v >= low && v <= high));
        if (!Number.isFinite(v) || v < low || v > high) return;   // still typing / out of range
        settings[key] = v;
        changed();
      });
    }

    const fillDefaults = () => {
      for (const [key, id] of Object.entries(cfg.inputs)) {
        settings[key] = defaults[group][key];
        document.getElementById(id).value = defaults[group][key];
        document.getElementById(id).classList.remove("invalid");
      }
    };

    button.addEventListener("click", () => {
      settings.enabled = !settings.enabled;
      // the first time it is turned on, start from the default values
      if (settings.enabled && Object.keys(cfg.inputs).some((k) => settings[k] === null)) fillDefaults();
      button.setAttribute("aria-pressed", String(settings.enabled));
      button.textContent = `${group === "friction" ? "Friction" : "Air resistance"}: ${settings.enabled ? "On" : "Off"}`;
      fields.hidden = !settings.enabled;
      changed();
    });
    document.getElementById(cfg.reset).addEventListener("click", () => { fillDefaults(); changed(); });
  }
  updatePhysicsSummary();
}

// One line under the physics buttons explaining what the settings mean
function updatePhysicsSummary() {
  const { friction, air } = state.physics;
  const el = document.getElementById("physics-summary");
  const parts = [];
  if (friction.enabled) parts.push(`Friction Force = ${friction.mu} × wheel load`);
  if (air.enabled) {
    const k = (0.5 * 1.225 * air.cd * air.area) / air.mass;
    parts.push(`Air Drag = ${(k * 625).toFixed(2)} m/s² at 25 m/s`);
  }
  el.textContent = parts.length
    ? `${parts.join("; ")}. Checks, stats, recommendations and the ride all use these.`
    : "Frictionless: no energy is lost (an upper limit on real speeds).";
}
