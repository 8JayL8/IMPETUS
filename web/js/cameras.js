// Camera modes: Orbit (around the track), Free (fly with WASD), Ride (sits in the front car).
import * as THREE from "three";
import { renderer, camera, controls } from "./scene.js";
import { ride, poseAt, CAR_LENGTH, CAR_HEIGHT } from "./ride.js";
import { RAIL_RADIUS } from "./constants.js";

let camMode = "orbit";
const camHint = document.getElementById("cam-hint");
const camSpeedEl = document.getElementById("cam-speed");
const camModeSel = document.getElementById("cam-mode");

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

export function setCameraMode(mode) {
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
export function initFreeSpeed(span) {
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

// Moves the camera for the current mode by one frame. Called from the animation loop.
export function updateCamera(dt) {
  if (camMode === "ride" && ride.sim) updateRideCamera();
  else if (camMode === "free") updateFreeCamera(dt);
  else controls.update();
}
