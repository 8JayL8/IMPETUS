// Draws a preview result everywhere: cards, 3D view, side profile, top view.
import { updateCards } from "./cards.js";
import { render3D } from "./track3d.js";
import { drawProfile, drawTopView } from "./views2d.js";

export function render(result) {
  updateCards(result);
  render3D(result);
  drawProfile(result);
  drawTopView(result);
}
