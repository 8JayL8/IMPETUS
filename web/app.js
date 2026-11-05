// IMPETUS web frontend.
// Every slider change rebuilds the whole track on the server (~10 ms), because a section's
// exit speed changes the physics checks of every section after it.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const SECTION_COLORS = {
  "Starts": "#2563eb",
  "Thrills 1": "#ea580c",
  "Turns": "#7c3aed",
  "Thrills 2": "#0d9488",
  "Ends": "#db2777",
};
const CONNECTOR_COLOR = "#9ca3af";   // the return track back to the station

// Starting layout shown when the page opens
const DEFAULTS = {
  "Starts": ["Lift Hill", 30],
  "Thrills 1": ["Loop", 23],
  "Turns": ["Helix", 15],
  "Thrills 2": ["Camelback", 27],
  "Ends": ["Brake", 20],
};

const STAT_LABELS = {
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

const statusEl = document.getElementById("status");
const state = {
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

// ========================================================================
//                              API helpers
// ========================================================================
async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function currentTracks() {
  return state.options.sections.map((section) => ({
    section,
    type: state.rows[section].type || null,
    value: state.rows[section].value,
  }));
}

function currentPhysics() {
  const { friction, air } = state.physics;
  return {
    friction: { enabled: friction.enabled, mu: friction.mu },
    air: { enabled: air.enabled, cd: air.cd, area: air.area, mass: air.mass },
  };
}

function physicsKey() {
  const { friction, air } = state.physics;
  return `${friction.enabled ? friction.mu : "-"}|${air.enabled ? [air.cd, air.area, air.mass].join(",") : "-"}`;
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle("error", isError);
}

// ========================================================================
//          Live preview: at most one request in flight, always the latest
// ========================================================================
let inFlight = false;
let pending = false;

function requestPreview() {
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

// Recommendations depend on 'Starts' (and, with friction / air resistance on, on the tracks picked
// before each section, since they slow the train down). They take longer, so wait until the user pauses.
let recTimer = null;
const recCache = new Map();

function lossesOn() {
  return state.physics.friction.enabled || state.physics.air.enabled;
}

function recKey() {
  const start = state.rows["Starts"];
  // Frictionless, the later picks don't change the recommendations, so they aren't part of the key
  const picks = lossesOn()
    ? currentTracks().filter((t) => t.section !== "Starts").map((t) => `${t.type || "-"}:${t.value}`).join(",")
    : "";
  return `${start.type}|${start.value}|${physicsKey()}|${picks}`;
}

function scheduleRecommendations() {
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

// ========================================================================
//                           Section cards
// ========================================================================
function buildCards() {
  const container = document.getElementById("sections");
  const template = document.getElementById("section-template");
  const [low, high] = state.options.value_range;

  for (const section of state.options.sections) {
    const card = template.content.firstElementChild.cloneNode(true);
    card.style.setProperty("--section-color", SECTION_COLORS[section]);
    card.querySelector(".card-name").textContent = section;

    const select = card.querySelector(".type-select");
    if (section !== "Starts") select.add(new Option("— none —", ""));
    for (const type of state.options.section_tracks[section]) select.add(new Option(type, type));

    const slider = card.querySelector(".value-slider");
    const input = card.querySelector(".value-input");
    for (const el of [slider, input]) { el.min = low; el.max = high; }

    const [defType, defValue] = DEFAULTS[section];
    const row = {
      type: defType, value: defValue,
      els: {
        card, select, slider, input,
        badge: card.querySelector(".badge"),
        valueLabel: card.querySelector(".value-label"),
        recLabel: card.querySelector(".rec-label"),
        warnings: card.querySelector(".warnings"),
        stats: card.querySelector(".stats dl"),
      },
    };
    state.rows[section] = row;
    select.value = defType;
    slider.value = input.value = defValue;

    const onValue = (raw, fromSlider) => {
      const v = parseFloat(raw);
      if (!Number.isFinite(v) || v < low || v > high) return;   // still typing
      row.value = v;
      if (fromSlider) input.value = v; else slider.value = v;
      requestPreview();
      if (section === "Starts" || lossesOn()) scheduleRecommendations();
    };
    slider.addEventListener("input", () => onValue(slider.value, true));
    input.addEventListener("input", () => onValue(input.value, false));
    select.addEventListener("change", () => {
      row.type = select.value || null;
      updateCardMode(section);
      updateRecommendationUI();
      requestPreview();
      if (section === "Starts" || lossesOn()) scheduleRecommendations();
    });

    updateCardMode(section);
    container.appendChild(card);
  }
}

function updateCardMode(section) {
  const row = state.rows[section];
  const { card, valueLabel } = row.els;
  card.classList.toggle("disabled", !row.type);
  const kind = state.options.length_tracks.includes(row.type) ? "Length" : "Height";
  valueLabel.textContent = row.type ? `Track ${kind} (meters)` : "Section skipped";
}

function updateRecommendationUI() {
  const [low, high] = state.options.value_range;
  const pct = (v) => `${((v - low) / (high - low)) * 100}%`;

  for (const section of state.options.sections) {
    if (section === "Starts") continue;
    const row = state.rows[section];
    const { slider, recLabel } = row.els;
    const bounds = state.recs && row.type ? state.recs.sections[section]?.[row.type] : undefined;

    recLabel.className = "rec-label";
    if (bounds === undefined) {
      slider.style.removeProperty("--rec-low");
      slider.style.removeProperty("--rec-high");
      recLabel.textContent = "";
    } else if (bounds === null) {
      slider.style.removeProperty("--rec-low");
      slider.style.removeProperty("--rec-high");
      recLabel.textContent = `No safe ${row.type} size for this start`;
      recLabel.classList.add("bad");
    } else {
      const [a, b] = bounds;
      // widened by half a step so a single recommended value is still visible
      slider.style.setProperty("--rec-low", pct(Math.max(low, a - 0.5)));
      slider.style.setProperty("--rec-high", pct(Math.min(high, b + 0.5)));
      recLabel.textContent = a === b ? `Recommended: ${a} m` : `Recommended: ${a} – ${b} m`;
      recLabel.classList.add("ok");
    }
  }
}

function updateCards(result) {
  const bySection = Object.fromEntries(result.sections.map((s) => [s.section, s]));

  for (const section of state.options.sections) {
    const { badge, warnings, stats } = state.rows[section].els;
    const info = bySection[section];
    badge.className = "badge";
    warnings.replaceChildren();
    stats.replaceChildren();
    if (!info) continue;

    if (section !== "Starts") {
      badge.classList.add(info.passed ? "ok" : "bad");
      badge.textContent = info.passed ? "PASS" : "FAIL";
    }
    for (const msg of info.warnings) {
      const li = document.createElement("li");
      li.textContent = msg;
      warnings.appendChild(li);
    }
    for (const [key, [label, unit]] of Object.entries(STAT_LABELS)) {
      const v = info.stats[key];
      if (v === null || v === undefined) continue;
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = unit ? `${v.toFixed(2)} ${unit}` : v.toFixed(3);
      stats.append(dt, dd);
    }
  }
}

// ========================================================================
//                              3D view
// ========================================================================
const view3d = document.getElementById("view3d");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
view3d.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color("#eef2f7");
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight("#ffffff", "#8a94a6", 2.2));
const sun = new THREE.DirectionalLight("#ffffff", 1.6);
sun.position.set(1, 2, 1.5);
scene.add(sun);

let trackGroup = new THREE.Group();
let grid = null;
scene.add(trackGroup);
let hasFitted = false;

function disposeGroup(group) {
  group.traverse((obj) => {
    obj.geometry?.dispose();
    if (obj.material) [].concat(obj.material).forEach((m) => { m.map?.dispose(); m.dispose(); });
  });
}

// Slices of the combined track: one per section, then the return track (if any)
function trackSlices(result) {
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

function slicePoints(track, from, to) {
  const pts = [];
  for (let i = Math.max(from, 0); i < to; i++) {
    const p = new THREE.Vector3(track.X[i], track.Y[i], track.Z[i]);
    if (!pts.length || p.distanceToSquared(pts[pts.length - 1]) > 1e-8) pts.push(p);   // drop repeated join points
  }
  return pts;
}

// ===== Track frames: forward / up / side at every point =====
const RAIL_GAUGE = 1.0;          // metres between the two rails
const RAIL_RADIUS = 0.07;
const SPINE_DROP = 0.45;         // spine sits this far below the rails
const SPINE_RADIUS = 0.16;

function computeFrames(track) {
  const n = track.X.length;
  const P = Array.from({ length: n }, (_, i) => new THREE.Vector3(track.X[i], track.Y[i], track.Z[i]));
  const forward = [], up = [], side = [];
  let prevUp = new THREE.Vector3(0, 1, 0);
  for (let i = 0; i < n; i++) {
    // central difference, skipping repeated points at section joins
    let a = i, b = i;
    while (a > 0 && P[a].distanceToSquared(P[i]) < 1e-8) a--;
    while (b < n - 1 && P[b].distanceToSquared(P[i]) < 1e-8) b++;
    const f = P[b].clone().sub(P[a]);
    if (f.lengthSq() < 1e-12) f.copy(forward[i - 1] || new THREE.Vector3(1, 0, 0));
    f.normalize();

    // the track's normal, made perpendicular to forward (falls back to the previous up)
    const u = new THREE.Vector3(track.Nx[i], track.Ny[i], track.Nz[i]);
    u.addScaledVector(f, -u.dot(f));
    if (u.lengthSq() < 1e-6) u.copy(prevUp).addScaledVector(f, -prevUp.dot(f));
    u.normalize();
    prevUp = u;

    forward.push(f);
    up.push(u);
    side.push(new THREE.Vector3().crossVectors(f, u).normalize());
  }
  return { P, forward, up, side };
}

function offsetTube(frames, from, to, sideOffset, upOffset, tubeRadius, material) {
  const pts = [];
  for (let i = Math.max(from, 0); i < to; i++) {
    const p = frames.P[i].clone().addScaledVector(frames.side[i], sideOffset).addScaledVector(frames.up[i], upOffset);
    if (!pts.length || p.distanceToSquared(pts[pts.length - 1]) > 1e-8) pts.push(p);
  }
  if (pts.length < 2) return;
  const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal");
  const geom = new THREE.TubeGeometry(curve, Math.min(pts.length * 2, 2400), tubeRadius, 6, false);
  trackGroup.add(new THREE.Mesh(geom, material));
}

function buildRails(track, frames, slice) {
  const railMat = new THREE.MeshStandardMaterial({ color: slice.color, roughness: 0.35, metalness: 0.3 });
  const spineMat = new THREE.MeshStandardMaterial({ color: slice.color, roughness: 0.6, metalness: 0.1 });
  offsetTube(frames, slice.from, slice.to, RAIL_GAUGE / 2, 0, RAIL_RADIUS, railMat);
  offsetTube(frames, slice.from, slice.to, -RAIL_GAUGE / 2, 0, RAIL_RADIUS, railMat);
  offsetTube(frames, slice.from, slice.to, 0, -SPINE_DROP, SPINE_RADIUS, spineMat);
}

// ===== Support columns =====
// Evenly spaced by distance along the track (not by point count), and a column is left out when:
//   - the track there is upside-down or near vertical (loop tops/sides, corkscrew rolls),
//   - another piece of track is directly underneath (it would go through the track),
//   - the track is right at ground level.
const SUPPORT_CLEARANCE = 1.4;   // m: no other track within this distance of a column (sideways)
const SUPPORT_MIN_HEIGHT = 1.2;  // m: lower than this, no column

function buildSupports(track, frames, groundY, span) {
  const n = track.X.length;
  const spacing = THREE.MathUtils.clamp(span / 30, 4, 10);

  // arc length, and a grid of track points by (x, z) to find track under a column quickly
  const S = new Float64Array(n);
  for (let i = 1; i < n; i++) S[i] = S[i - 1] + frames.P[i].distanceTo(frames.P[i - 1]);
  const cell = SUPPORT_CLEARANCE;
  const grid = new Map();
  const cellKey = (x, z) => `${Math.floor(x / cell)},${Math.floor(z / cell)}`;
  for (let i = 0; i < n; i++) {
    const k = cellKey(track.X[i], track.Z[i]);
    if (!grid.has(k)) grid.set(k, []);
    grid.get(k).push(i);
  }

  function trackBelow(i, x, z, topY) {
    const cx = Math.floor(x / cell), cz = Math.floor(z / cell);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dz = -1; dz <= 1; dz++) {
        for (const j of grid.get(`${cx + dx},${cz + dz}`) || []) {
          if (Math.abs(S[j] - S[i]) < 4) continue;   // the same stretch of track
          if (Math.hypot(track.X[j] - x, track.Z[j] - z) > SUPPORT_CLEARANCE) continue;
          if (track.Y[j] < topY - 0.5) return true;
        }
      }
    }
    return false;
  }

  const columns = [];
  let nextAt = spacing * 0.5;
  for (let i = 0; i < n; i++) {
    if (S[i] < nextAt) continue;
    const up = frames.up[i];
    const fwd = frames.forward[i];
    // attach under the spine
    const top = frames.P[i].clone().addScaledVector(up, -SPINE_DROP - SPINE_RADIUS);
    const height = top.y - groundY;

    const ok = up.y > 0.25                 // right way up (banked turns are fine)
      && Math.abs(fwd.y) < 0.8             // not climbing/diving near vertical
      && height > SUPPORT_MIN_HEIGHT
      && !trackBelow(i, top.x, top.z, top.y);
    if (!ok) continue;                     // try the next point instead
    columns.push({ x: top.x, z: top.z, top: top.y, height });
    nextAt = S[i] + spacing;
  }
  if (!columns.length) return;

  // one draw call for all columns, one for all footings
  const colMat = new THREE.MeshStandardMaterial({ color: "#8b95a5", roughness: 0.55, metalness: 0.35 });
  const footMat = new THREE.MeshStandardMaterial({ color: "#6b7280", roughness: 0.8 });
  const colMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(1, 1, 1, 10), colMat, columns.length);
  const footMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(1, 1, 1, 12), footMat, columns.length);
  const m = new THREE.Matrix4();
  columns.forEach((c, k) => {
    const r = THREE.MathUtils.clamp(0.12 + c.height * 0.006, 0.12, 0.35);   // taller columns are thicker
    m.makeScale(r, c.height, r).setPosition(c.x, groundY + c.height / 2, c.z);
    colMesh.setMatrixAt(k, m);
    m.makeScale(r * 2.4, 0.25, r * 2.4).setPosition(c.x, groundY + 0.125, c.z);
    footMesh.setMatrixAt(k, m);
  });
  trackGroup.add(colMesh, footMesh);
}

function render3D(result) {
  const { track } = result;
  scene.remove(trackGroup);
  disposeGroup(trackGroup);
  trackGroup = new THREE.Group();

  const box = new THREE.Box3();
  for (let i = 0; i < track.X.length; i++) box.expandByPoint(new THREE.Vector3(track.X[i], track.Y[i], track.Z[i]));
  const size = box.getSize(new THREE.Vector3());
  const span = Math.max(size.x, size.y, size.z, 1);
  const radius = Math.max(span * 0.004, 0.12);   // size of markers / arrows (not the rails)

  // Two running rails + a spine underneath, in the section's colour
  const frames = computeFrames(track);
  for (const slice of trackSlices(result)) buildRails(track, frames, slice);

  // The train rides on these frames
  updateRide(result, frames);

  const groundY = box.min.y;

  // Support columns down to the ground
  if (document.getElementById("show-supports").checked) buildSupports(track, frames, groundY, span);

  // Track normals (same red lines as the desktop app's 3D view)
  if (document.getElementById("show-normals").checked) {
    const verts = [];
    const len = span * 0.012;   // normal line length
    for (let i = 0; i < track.X.length; i++) {
      verts.push(track.X[i], track.Y[i], track.Z[i],
        track.X[i] + track.Nx[i] * len, track.Y[i] + track.Ny[i] * len, track.Z[i] + track.Nz[i] * len);
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    trackGroup.add(new THREE.LineSegments(geom, new THREE.LineBasicMaterial({ color: "#ef4444", transparent: true, opacity: 0.5 })));
  }

  // Start area, end (only when the track doesn't return to the station), direction arrows
  addStartMarker(track, radius, span, groundY);
  if (!hasReturnTrack(result)) addEndMarker(track, span);
  if (document.getElementById("show-direction").checked) addDirectionArrows(track, radius, span);

  scene.add(trackGroup);

  // Ground grid under the track
  if (grid) { scene.remove(grid); grid.geometry.dispose(); grid.material.dispose(); }
  const center = box.getCenter(new THREE.Vector3());
  const gridSize = Math.ceil((Math.max(size.x, size.z) * 1.4) / 10) * 10 || 10;
  grid = new THREE.GridHelper(gridSize, gridSize / 5, "#b6c0cf", "#d6dce5");
  grid.position.set(center.x, groundY - 0.01, center.z);
  scene.add(grid);

  if (!hasFitted) { fitCamera(box); hasFitted = true; }
  initFreeSpeed(span);
}

// ===== Start / end / direction markers =====
const START_COLOR = "#16a34a";
const END_COLOR = "#dc2626";
const ARROW_COLOR = "#0f172a";

function hasReturnTrack(result) {
  return trackSlices(result).some((s) => s.section === "Return");
}

const pointAt = (track, i) => new THREE.Vector3(track.X[i], track.Y[i], track.Z[i]);

// Direction of travel at point i (looks ahead past repeated points)
function directionAt(track, i) {
  const p = pointAt(track, i);
  for (let j = i + 1; j < track.X.length; j++) {
    const d = pointAt(track, j).sub(p);
    if (d.lengthSq() > 1e-8) return d.normalize();
  }
  for (let j = i - 1; j >= 0; j--) {   // last point: use the step coming into it
    const d = p.clone().sub(pointAt(track, j));
    if (d.lengthSq() > 1e-8) return d.normalize();
  }
  return new THREE.Vector3(1, 0, 0);
}

// A label that always faces the camera, anchored at its bottom centre
function textSprite(text, color, worldHeight) {
  const fontSize = 48;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const font = `bold ${fontSize}px system-ui, sans-serif`;
  ctx.font = font;
  canvas.width = Math.ceil(ctx.measureText(text).width) + 36;
  canvas.height = fontSize + 24;
  ctx.font = font;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(0, 0, canvas.width, canvas.height, 14);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 18, canvas.height / 2 + 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, depthTest: false }));
  sprite.scale.set(worldHeight * canvas.width / canvas.height, worldHeight, 1);
  sprite.center.set(0.5, 0);
  sprite.renderOrder = 10;
  return sprite;
}

// Label on a pole above a track point
function addLabel(text, color, base, span) {
  const poleHeight = span * 0.07;
  const top = base.clone().add(new THREE.Vector3(0, poleHeight, 0));
  const pole = new THREE.BufferGeometry().setFromPoints([base, top]);
  trackGroup.add(new THREE.Line(pole, new THREE.LineBasicMaterial({ color })));
  const label = textSprite(text, color, span * 0.035);
  label.position.copy(top);
  trackGroup.add(label);
}

// Station platform at the first track point, lined up with the starting direction
function addStartMarker(track, radius, span, groundY) {
  const p0 = pointAt(track, 0);
  const dir = directionAt(track, 0);
  const flatDir = new THREE.Vector3(dir.x, 0, dir.z);
  if (flatDir.lengthSq() < 1e-8) flatDir.set(1, 0, 0);
  flatDir.normalize();

  const length = Math.max(span * 0.06, 6);
  const width = Math.max(radius * 12, 2);
  const thickness = Math.max(radius * 1.2, 0.2);
  const platform = new THREE.Mesh(
    new THREE.BoxGeometry(length, thickness, width),
    new THREE.MeshStandardMaterial({ color: START_COLOR, transparent: true, opacity: 0.55, roughness: 0.8 }),
  );
  platform.position.set(p0.x, Math.max(groundY, p0.y - radius * 2) - thickness / 2, p0.z);
  platform.rotation.y = Math.atan2(-flatDir.z, flatDir.x);   // box length runs along X before rotating
  trackGroup.add(platform);

  addLabel("START", START_COLOR, p0.clone().add(new THREE.Vector3(0, radius * 2, 0)), span);
}

function addEndMarker(track, span) {
  const last = pointAt(track, track.X.length - 1);
  addLabel("END", END_COLOR, last, span);
}

// Cones pointing the way the train travels, spaced evenly along the track
function addDirectionArrows(track, radius, span) {
  const spacing = span / 14;
  const coneRadius = Math.max(radius * 1.4, 0.15);
  const geom = new THREE.ConeGeometry(coneRadius, coneRadius * 2.4, 14);
  const mat = new THREE.MeshStandardMaterial({ color: ARROW_COLOR, roughness: 0.5 });
  const up = new THREE.Vector3(0, 1, 0);

  let travelled = 0;
  let nextAt = spacing * 0.6;   // the first arrow sits just past the start
  for (let i = 1; i < track.X.length; i++) {
    travelled += pointAt(track, i).distanceTo(pointAt(track, i - 1));
    if (travelled < nextAt) continue;
    nextAt = travelled + spacing;

    const cone = new THREE.Mesh(geom, mat);
    const normal = new THREE.Vector3(track.Nx[i], track.Ny[i], track.Nz[i]);
    if (normal.lengthSq() > 1e-8) normal.normalize();
    // sit on top of the rail (along the track's up vector) so it isn't hidden inside the tube
    cone.position.copy(pointAt(track, i)).addScaledVector(normal, radius * 1.3);
    cone.quaternion.setFromUnitVectors(up, directionAt(track, i));
    trackGroup.add(cone);
  }
}

function fitCamera(box) {
  if (!box) {
    if (!state.lastResult) return;
    box = new THREE.Box3().setFromObject(trackGroup);
  }
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const dist = Math.max(size.x, size.y, size.z) * 1.3;
  camera.position.set(center.x - dist * 0.6, center.y + dist * 0.6, center.z + dist * 0.9);
  camera.near = dist / 500;
  camera.far = dist * 20;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

function resize3D() {
  const { clientWidth: w, clientHeight: h } = view3d;
  if (!w || !h) return;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

// ========================================================================
//                     Train ride (press Start in the 3D view)
// ========================================================================
// The speed at every point comes from the server (result.track.V): the same speeds the physics
// checks use, including friction / air resistance when they are on, plus the chain up the lift
// hill, the launch, the brakes and the slow roll back into the station.
// Where the speed is null the train has stopped: a failed velocity check (or the rollup doing its job).
const N_CARS = 4;
const CAR_LENGTH = 2.0, CAR_GAP = 0.35, CAR_WIDTH = 1.25, CAR_HEIGHT = 0.7;
const CAR_PITCH = CAR_LENGTH + CAR_GAP;
const TRAIN_LENGTH = N_CARS * CAR_PITCH;

const ride = {
  sim: null,          // per-point arc length + speed for the current track
  frames: null,
  s: 0,               // distance of the front car along the track (m)
  running: false,
  done: false,
  savedView: null,    // orbit camera to go back to after the ride cam
};

const rideBtn = document.getElementById("ride-btn");
const resetBtn = document.getElementById("ride-reset");
const rideSpeedSel = document.getElementById("ride-speed");
const hudSpeed = document.getElementById("hud-speed");
const hudSection = document.getElementById("hud-section");
const hudNote = document.getElementById("hud-note");

// ----- the train model -----
function makeCar(isFront) {
  const car = new THREE.Group();
  const bodyMat = new THREE.MeshStandardMaterial({ color: "#facc15", roughness: 0.4, metalness: 0.2 });
  const darkMat = new THREE.MeshStandardMaterial({ color: "#1f2937", roughness: 0.7 });

  const body = new THREE.Mesh(new THREE.BoxGeometry(CAR_LENGTH, CAR_HEIGHT * 0.55, CAR_WIDTH), bodyMat);
  body.position.y = CAR_HEIGHT * 0.1;
  car.add(body);

  // two rows of seats
  for (const x of [-0.45, 0.45]) {
    const seat = new THREE.Mesh(new THREE.BoxGeometry(0.12, CAR_HEIGHT * 0.6, CAR_WIDTH * 0.9), darkMat);
    seat.position.set(x - 0.3, CAR_HEIGHT * 0.55, 0);
    car.add(seat);
  }
  // wheels on each rail
  for (const x of [-CAR_LENGTH * 0.35, CAR_LENGTH * 0.35]) {
    for (const z of [-RAIL_GAUGE / 2, RAIL_GAUGE / 2]) {
      const wheel = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.22, 0.14), darkMat);
      wheel.position.set(x, -CAR_HEIGHT * 0.3, z);
      car.add(wheel);
    }
  }
  if (isFront) {
    const nose = new THREE.Mesh(new THREE.BoxGeometry(0.35, CAR_HEIGHT * 0.45, CAR_WIDTH * 0.8), bodyMat);
    nose.position.set(CAR_LENGTH / 2 + 0.15, CAR_HEIGHT * 0.05, 0);
    car.add(nose);
  }
  return car;
}

const train = new THREE.Group();
const cars = Array.from({ length: N_CARS }, (_, k) => makeCar(k === 0));
cars.forEach((c) => train.add(c));
train.visible = false;
scene.add(train);

// ----- speed along the track -----
function buildSim(result) {
  const { track } = result;
  const n = track.X.length;
  const S = new Float64Array(n);
  for (let i = 1; i < n; i++) {
    S[i] = S[i - 1] + Math.hypot(track.X[i] - track.X[i - 1], track.Y[i] - track.Y[i - 1], track.Z[i] - track.Z[i - 1]);
  }

  // which section every point belongs to
  const types = Object.fromEntries(result.sections.map((s) => [s.section, s.type]));
  const owner = new Array(n).fill("Return");
  for (const sl of trackSlices(result)) {
    if (sl.section === "Return") continue;
    for (let i = sl.from; i < sl.to; i++) owner[i] = sl.section;
  }

  const v = new Float64Array(n);
  let stallIndex = -1;
  for (let i = 0; i < n; i++) {
    const speed = track.V[i];
    if (speed === null || speed === undefined) { stallIndex = Math.max(i, 1); break; }
    v[i] = speed;
  }

  const end = stallIndex >= 0 ? stallIndex : n - 1;
  return { S, v, owner, types, stallIndex, sEnd: S[end], total: S[n - 1] };
}

// Index i with S[i] <= s < S[i+1]
function locate(S, s) {
  let lo = 0, hi = S.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (S[mid] <= s) lo = mid; else hi = mid;
  }
  return lo;
}

const _tmpQuat = new THREE.Quaternion();
const _tmpMat = new THREE.Matrix4();

// Position + orientation of the track at distance s
function poseAt(s) {
  const { S } = ride.sim;
  const f = ride.frames;
  s = THREE.MathUtils.clamp(s, 0, S[S.length - 1]);
  const i = locate(S, s);
  const j = Math.min(i + 1, S.length - 1);
  const t = S[j] > S[i] ? (s - S[i]) / (S[j] - S[i]) : 0;
  const pos = f.P[i].clone().lerp(f.P[j], t);
  const fwd = f.forward[i].clone().lerp(f.forward[j], t).normalize();
  const up = f.up[i].clone().lerp(f.up[j], t);
  up.addScaledVector(fwd, -up.dot(fwd)).normalize();
  const side = new THREE.Vector3().crossVectors(fwd, up).normalize();
  return { pos, fwd, up, side, i, t };
}

function speedAt(s) {
  const { S, v } = ride.sim;
  const i = locate(S, s);
  const j = Math.min(i + 1, S.length - 1);
  const t = S[j] > S[i] ? (s - S[i]) / (S[j] - S[i]) : 0;
  return v[i] + (v[j] - v[i]) * t;
}

function placeTrain() {
  if (!ride.sim) return;
  cars.forEach((car, k) => {
    const p = poseAt(ride.s - k * CAR_PITCH - CAR_LENGTH / 2);
    car.position.copy(p.pos).addScaledVector(p.up, RAIL_RADIUS + CAR_HEIGHT * 0.45);
    _tmpMat.makeBasis(p.fwd, p.up, p.side);
    car.quaternion.setFromRotationMatrix(_tmpMat);
  });
  train.visible = true;
}

function updateHud() {
  if (!ride.sim) return;
  const v = ride.running || ride.s > TRAIN_LENGTH + 0.01 ? speedAt(ride.s) : 0;
  hudSpeed.textContent = `${(v * 3.6).toFixed(0)} km/h  ·  ${v.toFixed(1)} m/s`;
  const section = ride.sim.owner[locate(ride.sim.S, ride.s)];
  hudSection.textContent = section === "Return" ? "Return to station" : `${section} – ${ride.sim.types[section]}`;
}

function resetRide() {
  ride.s = Math.min(TRAIN_LENGTH, ride.sim ? ride.sim.sEnd : TRAIN_LENGTH);
  ride.running = false;
  ride.done = false;
  hudNote.textContent = "";
  hudNote.className = "hud-note";
  rideBtn.textContent = "▶ Start";
  placeTrain();
  updateHud();
}

// Called after every track rebuild
function updateRide(result, frames) {
  const oldTotal = ride.sim ? ride.sim.total : 0;
  const wasMoving = ride.running || ride.done;
  ride.frames = frames;
  ride.sim = buildSim(result);

  if (!wasMoving) { resetRide(); return; }
  // keep the train at the same fraction of the ride while the track is being edited
  if (oldTotal > 0) ride.s = (ride.s / oldTotal) * ride.sim.total;
  ride.s = Math.min(ride.s, ride.sim.sEnd);
  if (ride.done && ride.s < ride.sim.sEnd) { ride.done = false; hudNote.textContent = ""; }
  placeTrain();
  updateHud();
}

function finishRide() {
  ride.running = false;
  ride.done = true;
  rideBtn.textContent = "↺ Again";
  const { stallIndex, owner, types } = ride.sim;
  const section = stallIndex >= 0 ? owner[stallIndex] : null;
  if (section && types[section] === "Rollup") {
    // a rollup is meant to stop the train
    hudNote.textContent = "Train came to a stop on the rollup.";
    hudNote.className = "hud-note ok";
  } else if (section) {
    const why = state.lastResult?.losses ? "not enough speed (with friction / air resistance)" : "not enough speed";
    hudNote.textContent = `Train stalled in ${section} (${types[section]}): ${why}.`;
    hudNote.className = "hud-note bad";
  } else {
    hudNote.textContent = "Ride complete!";
    hudNote.className = "hud-note ok";
  }
}

rideBtn.addEventListener("click", () => {
  if (!ride.sim) return;
  if (ride.done) resetRide();
  ride.running = !ride.running;
  rideBtn.textContent = ride.running ? "⏸ Pause" : "▶ Resume";
});
resetBtn.addEventListener("click", resetRide);

// ========================================================================
//          Camera modes: Orbit (around the track), Free (fly), Ride
// ========================================================================
let camMode = "orbit";
const camHint = document.getElementById("cam-hint");
const camSpeedEl = document.getElementById("cam-speed");

const free = {
  yaw: 0, pitch: 0,
  speed: 15,              // m/s, mouse wheel changes it
  keys: new Set(),
  dragging: false, lastX: 0, lastY: 0,
};

function lookDirection() {
  return camera.getWorldDirection(new THREE.Vector3());
}

// Free camera points where yaw/pitch say (no roll)
function applyFreeRotation() {
  camera.up.set(0, 1, 0);
  camera.rotation.order = "YXZ";
  camera.rotation.set(free.pitch, free.yaw, 0);
}

function setCameraMode(mode) {
  if (mode === camMode) return;
  const prev = camMode;
  const dir = lookDirection();

  if (prev === "orbit") ride.savedView = { pos: camera.position.clone(), target: controls.target.clone() };

  // leaving the ride cam: level the camera again
  camera.up.set(0, 1, 0);
  camera.near = 0.1;
  camera.updateProjectionMatrix();

  if (mode === "orbit") {
    if (prev === "free") {
      // orbit around the spot you were looking at
      const dist = ride.savedView ? ride.savedView.pos.distanceTo(ride.savedView.target) : 30;
      controls.target.copy(camera.position).addScaledVector(dir, dist);
    } else if (ride.savedView) {
      camera.position.copy(ride.savedView.pos);
      controls.target.copy(ride.savedView.target);
    }
    controls.enabled = true;
    controls.update();
  } else {
    controls.enabled = false;
  }

  if (mode === "free") {
    // start from wherever the camera is now, looking the same way
    free.yaw = Math.atan2(-dir.x, -dir.z);
    free.pitch = Math.asin(THREE.MathUtils.clamp(dir.y, -1, 1));
    applyFreeRotation();
  }

  camMode = mode;
  camModeSel.value = mode;
  camHint.hidden = mode !== "free";
  free.keys.clear();
  renderer.domElement.style.cursor = mode === "free" ? "grab" : "";
}

const camModeSel = document.getElementById("cam-mode");
camModeSel.addEventListener("change", () => {
  setCameraMode(camModeSel.value);
  camModeSel.blur();   // so W/A/S/D go to the camera, not the menu
});

// ----- free camera: drag to look -----
const canvasEl = renderer.domElement;
canvasEl.addEventListener("pointerdown", (e) => {
  if (camMode !== "free") return;
  free.dragging = true;
  free.lastX = e.clientX;
  free.lastY = e.clientY;
  canvasEl.setPointerCapture(e.pointerId);
  canvasEl.style.cursor = "grabbing";
});
canvasEl.addEventListener("pointermove", (e) => {
  if (camMode !== "free" || !free.dragging) return;
  const sens = 0.0035;
  free.yaw -= (e.clientX - free.lastX) * sens;
  free.pitch -= (e.clientY - free.lastY) * sens;
  free.pitch = THREE.MathUtils.clamp(free.pitch, -Math.PI / 2 + 0.01, Math.PI / 2 - 0.01);
  free.lastX = e.clientX;
  free.lastY = e.clientY;
  applyFreeRotation();
});
const stopLook = (e) => {
  if (!free.dragging) return;
  free.dragging = false;
  if (canvasEl.hasPointerCapture(e.pointerId)) canvasEl.releasePointerCapture(e.pointerId);
  if (camMode === "free") canvasEl.style.cursor = "grab";
};
canvasEl.addEventListener("pointerup", stopLook);
canvasEl.addEventListener("pointercancel", stopLook);

// ----- free camera: wheel = fly speed -----
canvasEl.addEventListener("wheel", (e) => {
  if (camMode !== "free") return;
  e.preventDefault();
  free.speed = THREE.MathUtils.clamp(free.speed * (e.deltaY < 0 ? 1.2 : 1 / 1.2), 1, 300);
  camSpeedEl.textContent = `${free.speed.toFixed(0)} m/s`;
}, { passive: false });

// ----- free camera: keyboard -----
const FREE_KEYS = new Set(["KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE", "KeyC", "Space", "ShiftLeft", "ShiftRight",
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);
window.addEventListener("keydown", (e) => {
  if (camMode !== "free" || !FREE_KEYS.has(e.code)) return;
  if (e.target.closest?.("input, select, textarea, dialog")) return;   // typing in a field
  e.preventDefault();
  free.keys.add(e.code);
});
window.addEventListener("keyup", (e) => free.keys.delete(e.code));
window.addEventListener("blur", () => free.keys.clear());

function updateFreeCamera(dt) {
  const k = free.keys;
  const forward = lookDirection();
  const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();
  const move = new THREE.Vector3();
  if (k.has("KeyW") || k.has("ArrowUp")) move.add(forward);
  if (k.has("KeyS") || k.has("ArrowDown")) move.sub(forward);
  if (k.has("KeyD") || k.has("ArrowRight")) move.add(right);
  if (k.has("KeyA") || k.has("ArrowLeft")) move.sub(right);
  if (k.has("KeyE") || k.has("Space")) move.y += 1;
  if (k.has("KeyQ") || k.has("KeyC")) move.y -= 1;
  if (move.lengthSq() === 0) return;
  const boost = k.has("ShiftLeft") || k.has("ShiftRight") ? 3 : 1;
  camera.position.addScaledVector(move.normalize(), free.speed * boost * dt);
}

// Fly speed suits the size of the track (set once, when the first track loads)
function initFreeSpeed(span) {
  if (free.speedSet) return;
  free.speed = THREE.MathUtils.clamp(span * 0.25, 5, 80);
  free.speedSet = true;
  camSpeedEl.textContent = `${free.speed.toFixed(0)} m/s`;
}

// ----- ride camera (sits in the front car) -----
function updateRideCamera() {
  const p = poseAt(ride.s - CAR_LENGTH * 0.6);
  const eye = p.pos.clone().addScaledVector(p.up, RAIL_RADIUS + CAR_HEIGHT + 0.9);
  const ahead = poseAt(ride.s + 12);
  const look = ahead.pos.clone().addScaledVector(ahead.up, 1.0);
  camera.position.copy(eye);
  camera.up.copy(p.up);
  camera.near = 0.05;
  camera.updateProjectionMatrix();
  camera.lookAt(look);
}

const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);

  if (ride.running && ride.sim) {
    const mul = parseFloat(rideSpeedSel.value);
    ride.s += Math.max(speedAt(ride.s), 0.4) * dt * mul;
    if (ride.s >= ride.sim.sEnd) { ride.s = ride.sim.sEnd; finishRide(); }
    placeTrain();
    updateHud();
  }

  if (camMode === "ride" && ride.sim) updateRideCamera();
  else if (camMode === "free") updateFreeCamera(dt);
  else controls.update();
  renderer.render(scene, camera);
});

// ========================================================================
//                       2D views (side profile, top)
// ========================================================================
function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const { clientWidth: w, clientHeight: h } = canvas;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

// Equal-aspect mapping from data coords to the canvas (y up)
function makeMapper(lines, w, h, pad = 28) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const { xs, ys } of lines) {
    for (let i = 0; i < xs.length; i++) {
      minX = Math.min(minX, xs[i]); maxX = Math.max(maxX, xs[i]);
      minY = Math.min(minY, ys[i]); maxY = Math.max(maxY, ys[i]);
    }
  }
  const scale = Math.min((w - 2 * pad) / Math.max(maxX - minX, 1e-6), (h - 2 * pad - 14) / Math.max(maxY - minY, 1e-6));
  const offX = (w - (maxX - minX) * scale) / 2;
  const offY = (h + 14 - (maxY - minY) * scale) / 2;
  return {
    x: (v) => offX + (v - minX) * scale,
    y: (v) => h - (offY + (v - minY) * scale),
    minY, maxY, minX, maxX,
  };
}

function drawLines(ctx, lines, map) {
  ctx.lineWidth = 2;
  ctx.lineJoin = "round";
  for (const { xs, ys, color } of lines) {
    ctx.strokeStyle = color;
    ctx.beginPath();
    for (let i = 0; i < xs.length; i++) {
      const px = map.x(xs[i]), py = map.y(ys[i]);
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    }
    ctx.stroke();
  }
}

function drawDot(ctx, x, y) {
  ctx.fillStyle = "#111827";
  ctx.beginPath();
  ctx.arc(x, y, 3.5, 0, Math.PI * 2);
  ctx.fill();
}

// Arrowheads every `spacing` screen pixels along the lines, pointing the way the train travels
function drawArrows(ctx, lines, map, spacing = 70) {
  if (!document.getElementById("show-direction").checked) return;
  let untilNext = spacing * 0.6;
  ctx.fillStyle = ARROW_COLOR;
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 1.5;
  for (const { xs, ys } of lines) {
    for (let i = 1; i < xs.length; i++) {
      const x0 = map.x(xs[i - 1]), y0 = map.y(ys[i - 1]);
      const x1 = map.x(xs[i]), y1 = map.y(ys[i]);
      const seg = Math.hypot(x1 - x0, y1 - y0);
      if (seg < 1e-6) continue;
      let t = untilNext;
      while (t <= seg) {
        const px = x0 + (x1 - x0) * (t / seg), py = y0 + (y1 - y0) * (t / seg);
        ctx.save();
        ctx.translate(px, py);
        ctx.rotate(Math.atan2(y1 - y0, x1 - x0));
        ctx.beginPath();
        ctx.moveTo(4.5, 0);
        ctx.lineTo(-3.5, -3.5);
        ctx.lineTo(-1.5, 0);
        ctx.lineTo(-3.5, 3.5);
        ctx.closePath();
        ctx.stroke();
        ctx.fill();
        ctx.restore();
        t += spacing;
      }
      untilNext = t - seg;
    }
  }
}

// Coloured marker with a text tag (START / END)
function drawTag(ctx, x, y, text, color, w) {
  ctx.fillStyle = color;
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(x, y, 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.font = "bold 11px system-ui, sans-serif";
  const tw = ctx.measureText(text).width + 10;
  let tx = x - tw / 2;
  tx = Math.min(Math.max(tx, 2), w - tw - 2);   // keep the tag inside the canvas
  const ty = Math.max(y - 26, 2);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(tx, ty, tw, 16, 4);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "middle";
  ctx.fillText(text, tx + 5, ty + 8.5);
  ctx.textBaseline = "alphabetic";
}

function drawProfile(result) {
  const { ctx, w, h } = setupCanvas(document.getElementById("profile"));
  // Same as the desktop app: each section's distance continues from where the last one ended
  let offset = 0;
  const lines = result.profile.map((seg) => {
    const xs = seg.XY.map((v) => v + offset);
    offset = xs[xs.length - 1];
    return { xs, ys: seg.Z, color: SECTION_COLORS[seg.section] };
  });
  if (!lines.length) return;
  const map = makeMapper(lines, w, h);

  // ground line + height labels
  ctx.strokeStyle = "#cbd5e1";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(map.x(map.minX), map.y(map.minY));
  ctx.lineTo(map.x(map.maxX), map.y(map.minY));
  ctx.stroke();
  ctx.fillStyle = "#6b7280";
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillText(`${map.maxY.toFixed(1)} m`, 6, map.y(map.maxY) + 4);
  ctx.fillText(`${(map.maxX - map.minX).toFixed(0)} m long`, w - 80, h - 8);

  drawLines(ctx, lines, map);
  drawArrows(ctx, lines, map);
  for (const line of lines.slice(0, -1)) drawDot(ctx, map.x(line.xs[line.xs.length - 1]), map.y(line.ys[line.ys.length - 1]));

  const first = lines[0], last = lines[lines.length - 1];
  if (!hasReturnTrack(result)) {
    drawTag(ctx, map.x(last.xs[last.xs.length - 1]), map.y(last.ys[last.ys.length - 1]), "END", END_COLOR, w);
  }
  drawTag(ctx, map.x(first.xs[0]), map.y(first.ys[0]), "START", START_COLOR, w);
}

function drawTopView(result) {
  const { ctx, w, h } = setupCanvas(document.getElementById("topview"));
  const { track } = result;
  const lines = trackSlices(result).map((s) => {
    const from = Math.max(s.from, 0);
    return { xs: track.X.slice(from, s.to), ys: track.Z.slice(from, s.to), color: s.color };
  }).filter((l) => l.xs.length > 1);
  if (!lines.length) return;
  const map = makeMapper(lines, w, h);
  drawLines(ctx, lines, map);
  drawArrows(ctx, lines, map);
  const slices = trackSlices(result);
  for (const s of result.sections.slice(0, -1)) {
    const i = slices.find((t) => t.section === s.section).to - 1;
    drawDot(ctx, map.x(track.X[i]), map.y(track.Z[i]));
  }

  const n = track.X.length - 1;
  if (!hasReturnTrack(result)) drawTag(ctx, map.x(track.X[n]), map.y(track.Z[n]), "END", END_COLOR, w);
  drawTag(ctx, map.x(track.X[0]), map.y(track.Z[0]), "START", START_COLOR, w);
}

// ========================================================================
//                              Render all
// ========================================================================
function render(result) {
  updateCards(result);
  render3D(result);
  drawProfile(result);
  drawTopView(result);
}

const viewsObserver = new ResizeObserver(() => {
  resize3D();
  if (state.lastResult) { drawProfile(state.lastResult); drawTopView(state.lastResult); }
});
viewsObserver.observe(document.querySelector(".views"));
viewsObserver.observe(view3d);   // also redraw when the bottom panel is dragged

// ========================================================================
//        Drag handles: resize, hide (drag closed) or show the side panels
// ========================================================================
// Dragging a handle resizes its panel. Dragging past `collapseAt` hides the panel;
// dragging the handle back out (or double-clicking it) shows it again.
// Sizes are remembered in localStorage.
function makeSplitter({ handle, panel, axis, min, max, collapseAt, defaultSize, key }) {
  const prop = axis === "x" ? "width" : "height";
  const saved = JSON.parse(localStorage.getItem(key) || "null");
  let size = saved?.size ?? defaultSize;   // last open size
  let collapsed = saved?.collapsed ?? false;

  function apply() {
    panel.style[prop] = `${size}px`;
    panel.classList.toggle("collapsed", collapsed);
    handle.classList.toggle("collapsed", collapsed);
    handle.setAttribute("aria-expanded", String(!collapsed));
  }
  const save = () => localStorage.setItem(key, JSON.stringify({ size, collapsed }));

  // Size the panel would have with the pointer at (x, y)
  function sizeFromPointer(event) {
    if (axis === "x") return event.clientX - panel.getBoundingClientRect().left;
    const container = panel.parentElement.getBoundingClientRect();
    return container.bottom - 12 - event.clientY;   // 12 = .views bottom padding
  }

  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    handle.classList.add("dragging");
    document.body.classList.add("resizing", axis === "x" ? "resizing-col" : "resizing-row");
  });

  handle.addEventListener("pointermove", (event) => {
    if (!handle.hasPointerCapture(event.pointerId)) return;
    const wanted = sizeFromPointer(event);
    if (wanted < collapseAt) {
      collapsed = true;
    } else {
      collapsed = false;
      size = Math.round(THREE.MathUtils.clamp(wanted, min, max()));
    }
    apply();
  });

  const endDrag = (event) => {
    if (!handle.hasPointerCapture(event.pointerId)) return;
    handle.releasePointerCapture(event.pointerId);
    handle.classList.remove("dragging");
    document.body.classList.remove("resizing", "resizing-col", "resizing-row");
    save();
  };
  handle.addEventListener("pointerup", endDrag);
  handle.addEventListener("pointercancel", endDrag);

  handle.addEventListener("dblclick", () => {
    collapsed = !collapsed;
    apply();
    save();
  });

  apply();
}

makeSplitter({
  handle: document.getElementById("split-left"),
  panel: document.getElementById("sections"),
  axis: "x",
  min: 220,
  max: () => Math.min(560, window.innerWidth * 0.5),
  collapseAt: 120,
  defaultSize: 300,
  key: "impetus.leftPanel",
});

makeSplitter({
  handle: document.getElementById("split-bottom"),
  panel: document.querySelector(".panel-row"),
  axis: "y",
  min: 120,
  max: () => document.querySelector(".views").clientHeight - 180,   // leave room for the 3D view
  collapseAt: 60,
  defaultSize: 260,
  key: "impetus.bottomPanel",
});

// Fit view always goes back to the orbit camera
document.getElementById("fit-btn").addEventListener("click", () => { setCameraMode("orbit"); fitCamera(); });
for (const id of ["show-normals", "show-supports", "show-direction"]) {
  document.getElementById(id).addEventListener("change", () => state.lastResult && render(state.lastResult));
}

// ========================================================================
//                              Export
// ========================================================================
const dialog = document.getElementById("export-dialog");
const exportForm = document.getElementById("export-form");
const exportResult = document.getElementById("export-result");

document.getElementById("export-btn").addEventListener("click", () => {
  exportResult.textContent = "";
  exportResult.className = "hint";
  dialog.showModal();
});

document.getElementById("export-go").addEventListener("click", async (event) => {
  event.preventDefault();
  if (!exportForm.reportValidity()) return;
  const form = new FormData(exportForm);
  const body = {
    tracks: currentTracks(),
    physics: currentPhysics(),
    section_folder: form.get("section_folder"),
    coaster_name: form.get("coaster_name"),
    overwrite: false,
  };
  try {
    let result = await api("/api/export", body);
    if (result.exists) {
      if (!confirm(`"${result.coaster_name}" already exists in "${result.section_folder}". Replace the previous build?`)) return;
      result = await api("/api/export", { ...body, overwrite: true });
    }
    const failed = result.sections.filter((s) => !s.passed).map((s) => s.section);
    exportResult.className = "hint ok";
    exportResult.textContent = `Saved ${result.saved_to.coaster_csv}` +
      (failed.length ? ` (warning: ${failed.join(", ")} failed physics checks)` : "");
  } catch (err) {
    exportResult.className = "hint error";
    exportResult.textContent = err.message;
  }
});

// ========================================================================
//          Physics panel: friction + air resistance (off = frictionless)
// ========================================================================
const PHYSICS_FIELDS = {
  friction: { button: "friction-btn", fields: "friction-fields", reset: "friction-reset", inputs: { mu: "mu-input" } },
  air: { button: "air-btn", fields: "air-fields", reset: "air-reset",
         inputs: { cd: "cd-input", area: "area-input", mass: "mass-input" } },
};

function setupPhysicsPanel() {
  const defaults = state.options.physics_defaults;
  const limits = state.options.physics_limits;
  let timer = null;
  const changed = () => {
    updatePhysicsSummary();
    clearTimeout(timer);
    timer = setTimeout(() => { requestPreview(); scheduleRecommendations(); }, 120);
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
  if (friction.enabled) parts.push(`friction force = ${friction.mu} × wheel load`);
  if (air.enabled) {
    const k = (0.5 * 1.225 * air.cd * air.area) / air.mass;
    parts.push(`air drag = ${(k * 625).toFixed(2)} m/s² at 25 m/s`);
  }
  el.textContent = parts.length
    ? `${parts.join("; ")}. Checks, stats, recommendations and the ride all use these.`
    : "Frictionless: no energy is lost (an upper limit on real speeds).";
}

// ========================================================================
//                              Start up
// ========================================================================
(async () => {
  try {
    state.options = await api("/api/options");
  } catch (err) {
    setStatus(`Can't reach the server: ${err.message}`, true);
    return;
  }
  setupPhysicsPanel();
  buildCards();
  resize3D();
  requestPreview();
  scheduleRecommendations();
})();
