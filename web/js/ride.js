// Train ride (press Start in the 3D view).
// The speed at every point comes from the server (result.track.V): the same speeds the physics
// checks use, including friction / air resistance when they are on, plus the chain up the lift
// hill, the launch, the brakes and the slow roll back into the station.
// Where the speed is null the train has stopped: a failed velocity check (or the rollup doing its job).
import * as THREE from "three";
import { scene } from "./scene.js";
import { state, trackSlices } from "./state.js";
import { RAIL_GAUGE, RAIL_RADIUS } from "./constants.js";

const N_CARS = 4;
export const CAR_LENGTH = 2.0, CAR_HEIGHT = 0.7;
const CAR_GAP = 0.35, CAR_WIDTH = 1.25;
const CAR_PITCH = CAR_LENGTH + CAR_GAP;
const TRAIN_LENGTH = N_CARS * CAR_PITCH;

export const ride = {
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

const _tmpMat = new THREE.Matrix4();

// Position + orientation of the track at distance s
export function poseAt(s) {
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
export function updateRide(result, frames) {
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

// Moves the train forward by one frame (dt seconds). Called from the animation loop.
export function stepRide(dt) {
  if (!ride.running || !ride.sim) return;
  const mul = parseFloat(rideSpeedSel.value);
  ride.s += Math.max(speedAt(ride.s), 0.4) * dt * mul;
  if (ride.s >= ride.sim.sEnd) { ride.s = ride.sim.sEnd; finishRide(); }
  placeTrain();
  updateHud();
}

rideBtn.addEventListener("click", () => {
  if (!ride.sim) return;
  if (ride.done) resetRide();
  ride.running = !ride.running;
  rideBtn.textContent = ride.running ? "⏸ Pause" : "▶ Resume";
});
resetBtn.addEventListener("click", resetRide);
