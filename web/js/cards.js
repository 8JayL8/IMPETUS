// Section cards in the left panel: track type, value slider, recommendations, stats and warnings.
import { SECTION_COLORS, DEFAULTS, STAT_LABELS } from "./constants.js";
import { state } from "./state.js";

// onChange(section) is called whenever a card's track type or value changes
export function buildCards(onChange) {
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
      onChange(section);
    };
    slider.addEventListener("input", () => onValue(slider.value, true));
    input.addEventListener("input", () => onValue(input.value, false));
    select.addEventListener("change", () => {
      row.type = select.value || null;
      updateCardMode(section);
      updateRecommendationUI();
      onChange(section);
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

export function updateRecommendationUI() {
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

export function updateCards(result) {
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
