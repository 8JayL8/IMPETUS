// IMPETUS web frontend: entry point. Wires the modules together and starts the page.
import * as THREE from "three";
import { api, setStatus } from "./api.js";
import { state } from "./state.js";
import { renderer, scene, camera, view3d, resize3D } from "./scene.js";
import { fitCamera, G_BANDS } from "./track3d.js";
import { stepRide } from "./ride.js";
import { setCameraMode, updateCamera } from "./cameras.js";
import { drawProfile, drawTopView } from "./views2d.js";
import { buildCards } from "./cards.js";
import { setupPhysicsPanel } from "./physicsPanel.js";
import { setupExportDialog } from "./exportDialog.js";
import { setupSplitters } from "./splitters.js";
import { requestPreview, scheduleRecommendations, tracksChanged } from "./preview.js";
import { render } from "./render.js";

// ===== Animation loop: move the train, move the camera, draw =====
const clock = new THREE.Clock();
renderer.setAnimationLoop(() => {
  const dt = Math.min(clock.getDelta(), 0.05);
  stepRide(dt);
  updateCamera(dt);
  renderer.render(scene, camera);
});

// ===== Redraw when the panels change size =====
const viewsObserver = new ResizeObserver(() => {
  resize3D();
  if (state.lastResult) { drawProfile(state.lastResult); drawTopView(state.lastResult); }
});
viewsObserver.observe(document.querySelector(".views"));
viewsObserver.observe(view3d);   // also redraw when the bottom panel is dragged

setupSplitters();
setupExportDialog();

// ===== Normal force legend (same colours as the lines) =====
for (const [, color, text] of G_BANDS) {
  const li = document.createElement("li");
  const swatch = document.createElement("span");
  swatch.style.setProperty("--swatch", color);
  li.append(swatch, text);
  document.getElementById("g-legend-items").appendChild(li);
}

// ===== Header buttons =====
// Fit view always goes back to the orbit camera
document.getElementById("fit-btn").addEventListener("click", () => { setCameraMode("orbit"); fitCamera(); });
for (const id of ["show-normals", "show-supports", "show-direction"]) {
  document.getElementById(id).addEventListener("change", () => state.lastResult && render(state.lastResult));
}

// ===== Start up =====
(async () => {
  try {
    state.options = await api("/api/options");
  } catch (err) {
    setStatus(`Can't reach the server: ${err.message}`, true);
    return;
  }
  setupPhysicsPanel(() => { requestPreview(); scheduleRecommendations(); });
  buildCards(tracksChanged);
  resize3D();
  requestPreview();
  scheduleRecommendations();
})();
