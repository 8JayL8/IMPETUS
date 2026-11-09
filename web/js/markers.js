// 3D markers: START platform, END label, and direction arrows along the track.
// Each function adds its objects to the given group.
import * as THREE from "three";
import { START_COLOR, END_COLOR, ARROW_COLOR } from "./constants.js";

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
function addLabel(group, text, color, base, span) {
  const poleHeight = span * 0.07;
  const top = base.clone().add(new THREE.Vector3(0, poleHeight, 0));
  const pole = new THREE.BufferGeometry().setFromPoints([base, top]);
  group.add(new THREE.Line(pole, new THREE.LineBasicMaterial({ color })));
  const label = textSprite(text, color, span * 0.035);
  label.position.copy(top);
  group.add(label);
}

// Station platform at the first track point, lined up with the starting direction
export function addStartMarker(group, track, radius, span, groundY) {
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
  group.add(platform);

  addLabel(group, "START", START_COLOR, p0.clone().add(new THREE.Vector3(0, radius * 2, 0)), span);
}

export function addEndMarker(group, track, span) {
  const last = pointAt(track, track.X.length - 1);
  addLabel(group, "END", END_COLOR, last, span);
}

// Cones pointing the way the train travels, spaced evenly along the track
export function addDirectionArrows(group, track, radius, span) {
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
    group.add(cone);
  }
}
