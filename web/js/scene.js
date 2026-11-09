// The Three.js renderer, scene, camera and orbit controls for the 3D view.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

export const view3d = document.getElementById("view3d");
export const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
view3d.appendChild(renderer.domElement);

export const scene = new THREE.Scene();
scene.background = new THREE.Color("#eef2f7");
export const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
export const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.HemisphereLight("#ffffff", "#8a94a6", 2.2));
const sun = new THREE.DirectionalLight("#ffffff", 1.6);
sun.position.set(1, 2, 1.5);
scene.add(sun);

export function resize3D() {
  const { clientWidth: w, clientHeight: h } = view3d;
  if (!w || !h) return;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
