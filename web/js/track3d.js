// The 3D track: rails, spine, support columns, normals, ground grid, and fitting the camera.
import * as THREE from "three";
import { scene, camera, controls } from "./scene.js";
import { state, trackSlices, hasReturnTrack } from "./state.js";
import { RAIL_GAUGE, RAIL_RADIUS, SPINE_DROP, SPINE_RADIUS } from "./constants.js";
import { addStartMarker, addEndMarker, addDirectionArrows } from "./markers.js";
import { updateRide } from "./ride.js";
import { initFreeSpeed } from "./cameras.js";

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

// ===== Track frames: forward / up / side at every point =====
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

function offsetTube(group, frames, from, to, sideOffset, upOffset, tubeRadius, material) {
  const pts = [];
  for (let i = Math.max(from, 0); i < to; i++) {
    const p = frames.P[i].clone().addScaledVector(frames.side[i], sideOffset).addScaledVector(frames.up[i], upOffset);
    if (!pts.length || p.distanceToSquared(pts[pts.length - 1]) > 1e-8) pts.push(p);
  }
  if (pts.length < 2) return;
  const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal");
  const geom = new THREE.TubeGeometry(curve, Math.min(pts.length * 2, 2400), tubeRadius, 6, false);
  group.add(new THREE.Mesh(geom, material));
}

function buildRails(group, frames, slice) {
  const railMat = new THREE.MeshStandardMaterial({ color: slice.color, roughness: 0.35, metalness: 0.3 });
  const spineMat = new THREE.MeshStandardMaterial({ color: slice.color, roughness: 0.6, metalness: 0.1 });
  offsetTube(group, frames, slice.from, slice.to, RAIL_GAUGE / 2, 0, RAIL_RADIUS, railMat);
  offsetTube(group, frames, slice.from, slice.to, -RAIL_GAUGE / 2, 0, RAIL_RADIUS, railMat);
  offsetTube(group, frames, slice.from, slice.to, 0, -SPINE_DROP, SPINE_RADIUS, spineMat);
}

// ===== Support columns =====
// Evenly spaced by distance along the track (not by point count), and a column is left out when:
//   - the track there is upside-down or near vertical (loop tops/sides, corkscrew rolls),
//   - another piece of track is directly underneath (it would go through the track),
//   - the track is right at ground level.
const SUPPORT_CLEARANCE = 1.4;   // m: no other track within this distance of a column (sideways)
const SUPPORT_MIN_HEIGHT = 1.2;  // m: lower than this, no column

function buildSupports(group, track, frames, groundY, span) {
  const n = track.X.length;
  const spacing = THREE.MathUtils.clamp(span / 30, 4, 10);

  // arc length, and a grid of track points by (x, z) to find track under a column quickly
  const S = new Float64Array(n);
  for (let i = 1; i < n; i++) S[i] = S[i - 1] + frames.P[i].distanceTo(frames.P[i - 1]);
  const cell = SUPPORT_CLEARANCE;
  const cells = new Map();
  const cellKey = (x, z) => `${Math.floor(x / cell)},${Math.floor(z / cell)}`;
  for (let i = 0; i < n; i++) {
    const k = cellKey(track.X[i], track.Z[i]);
    if (!cells.has(k)) cells.set(k, []);
    cells.get(k).push(i);
  }

  function trackBelow(i, x, z, topY) {
    const cx = Math.floor(x / cell), cz = Math.floor(z / cell);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dz = -1; dz <= 1; dz++) {
        for (const j of cells.get(`${cx + dx},${cz + dz}`) || []) {
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
  group.add(colMesh, footMesh);
}

// Track normals (same red lines as the desktop app's 3D view)
function buildNormals(group, track, span) {
  const verts = [];
  const len = span * 0.012;   // normal line length
  for (let i = 0; i < track.X.length; i++) {
    verts.push(track.X[i], track.Y[i], track.Z[i],
      track.X[i] + track.Nx[i] * len, track.Y[i] + track.Ny[i] * len, track.Z[i] + track.Nz[i] * len);
  }
  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
  group.add(new THREE.LineSegments(geom, new THREE.LineBasicMaterial({ color: "#ef4444", transparent: true, opacity: 0.5 })));
}

export function render3D(result) {
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
  for (const slice of trackSlices(result)) buildRails(trackGroup, frames, slice);

  // The train rides on these frames
  updateRide(result, frames);

  const groundY = box.min.y;

  // Support columns down to the ground
  if (document.getElementById("show-supports").checked) buildSupports(trackGroup, track, frames, groundY, span);
  if (document.getElementById("show-normals").checked) buildNormals(trackGroup, track, span);

  // Start area, end (only when the track doesn't return to the station), direction arrows
  addStartMarker(trackGroup, track, radius, span, groundY);
  if (!hasReturnTrack(result)) addEndMarker(trackGroup, track, span);
  if (document.getElementById("show-direction").checked) addDirectionArrows(trackGroup, track, radius, span);

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

// Point the orbit camera at the whole track (or at `box` if given)
export function fitCamera(box) {
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
