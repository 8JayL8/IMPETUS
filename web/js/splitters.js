// Drag handles: resize, hide (drag closed) or show the side panels.
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
      size = Math.round(Math.min(Math.max(wanted, min), max()));
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

export function setupSplitters() {
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
}
