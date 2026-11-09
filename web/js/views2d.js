// 2D views in the bottom panel: side profile and top view (drawn on <canvas>).
import { SECTION_COLORS, START_COLOR, END_COLOR, ARROW_COLOR } from "./constants.js";
import { trackSlices, hasReturnTrack } from "./state.js";

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

export function drawProfile(result) {
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

export function drawTopView(result) {
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
