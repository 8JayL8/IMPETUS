// Export dialog: saves the coaster as a NoLimits 2 CSV on the server.
import { api } from "./api.js";
import { currentTracks, currentPhysics } from "./state.js";

export function setupExportDialog() {
  const dialog = document.getElementById("export-dialog");
  const exportForm = document.getElementById("export-form");
  const exportResult = document.getElementById("export-result");

  document.getElementById("export-btn").addEventListener("click", () => {
    exportResult.textContent = "";
    exportResult.className = "hint";
    dialog.showModal();
  });

  document.getElementById("export-go").addEventListener("click", async (event) => {
    event.preventDefault();
    if (!exportForm.reportValidity()) return;
    const form = new FormData(exportForm);
    const body = {
      tracks: currentTracks(),
      physics: currentPhysics(),
      section_folder: form.get("section_folder"),
      coaster_name: form.get("coaster_name"),
      overwrite: false,
    };
    try {
      let result = await api("/api/export", body);
      if (result.exists) {
        if (!confirm(`"${result.coaster_name}" already exists in "${result.section_folder}". Replace the previous build?`)) return;
        result = await api("/api/export", { ...body, overwrite: true });
      }
      const failed = result.sections.filter((s) => !s.passed).map((s) => s.section);
      exportResult.className = "hint ok";
      exportResult.textContent = `Saved ${result.saved_to.coaster_csv}` +
        (failed.length ? ` (warning: ${failed.join(", ")} failed physics checks)` : "");
    } catch (err) {
      exportResult.className = "hint error";
      exportResult.textContent = err.message;
    }
  });
}
