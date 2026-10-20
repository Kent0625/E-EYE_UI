// Client-side interactions for Settings Screen
import { getJson, postJson } from "./api.js";
import { t, setLanguage } from "./i18n.js";

document.addEventListener("DOMContentLoaded", () => {
  // 1. Site Name Saving
  const btnSaveSite = document.getElementById("btn-save-site");
  const siteInput = document.getElementById("setting-site-name");
  const siteFeedback = document.getElementById("site-save-feedback");

  if (btnSaveSite && siteInput) {
    const siteError = document.getElementById("site-save-error");
    btnSaveSite.addEventListener("click", async () => {
      const siteName = siteInput.value.trim();
      if (siteError) siteError.classList.add("hidden");
      try {
        await postJson("/api/settings", { site_name: siteName });
        if (siteFeedback) {
          siteFeedback.classList.remove("hidden");
          setTimeout(() => {
            siteFeedback.classList.add("hidden");
          }, 3500);
        }
      } catch (err) {
        console.error("Failed to save site name:", err);
        if (siteError) {
          siteError.textContent = err.message || "Failed to save site name. Please try again.";
          siteError.classList.remove("hidden");
        }
      }
    });
  }

  // 2. Clock Synchronization
  const btnSyncClock = document.getElementById("btn-sync-clock");
  const clockWarning = document.getElementById("clock-warning");
  const clockFeedback = document.getElementById("clock-sync-feedback");
  const clockError = document.getElementById("clock-sync-error");

  if (btnSyncClock) {
    btnSyncClock.addEventListener("click", async () => {
      if (clockError) clockError.classList.add("hidden");
      try {
        const clientIso = new Date().toISOString();
        await postJson("/api/clock", { iso_timestamp: clientIso });
        if (clockWarning) {
          clockWarning.classList.add("hidden");
        }
        if (clockFeedback) {
          clockFeedback.classList.remove("hidden");
          setTimeout(() => {
            clockFeedback.classList.add("hidden");
          }, 4000);
        }
      } catch (err) {
        console.error("Failed to sync clock:", err);
        if (clockError) {
          clockError.textContent = err.message || "Failed to synchronize clock. Please try again.";
          clockError.classList.remove("hidden");
        }
      }
    });
  }

  // 3. Language Selection inside Settings
  const langBtns = document.querySelectorAll(".settings-lang-btn");
  langBtns.forEach(btn => {
    btn.addEventListener("click", async () => {
      const lang = btn.getAttribute("data-lang");
      if (lang) {
        langBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        setLanguage(lang);
        try {
          await postJson("/api/settings", { lang });
        } catch (e) {
          console.error("Failed to persist language:", e);
        }
      }
    });
  });

  // 4. Research Mode Toggle
  const researchToggle = document.getElementById("toggle-research-mode");
  const researchFeedback = document.getElementById("research-mode-feedback");
  if (researchToggle) {
    researchToggle.addEventListener("change", async (e) => {
      const isChecked = e.target.checked;
      try {
        await postJson("/api/settings", { research_mode: isChecked ? "1" : "0" });
        if (researchFeedback) {
          researchFeedback.textContent = isChecked ? "Research mode enabled." : "Research mode disabled.";
          researchFeedback.classList.remove("hidden");
          setTimeout(() => {
            researchFeedback.classList.add("hidden");
          }, 3000);
        }
      } catch (err) {
        console.error("Failed to toggle research mode:", err);
      }
    });
  }

  // 5. Delete All Sessions Modal Flow
  const btnDeleteAll = document.getElementById("btn-delete-all");
  const deleteAllModal = document.getElementById("delete-all-modal");
  const btnCancelDeleteAll = document.getElementById("btn-cancel-delete-all");
  const btnConfirmDeleteAll = document.getElementById("btn-confirm-delete-all");
  const dataFeedback = document.getElementById("data-delete-feedback");

  const dataError = document.getElementById("data-delete-error");

  if (btnDeleteAll && deleteAllModal) {
    btnDeleteAll.addEventListener("click", () => {
      if (dataError) dataError.classList.add("hidden");
      deleteAllModal.classList.remove("hidden");
      if (btnCancelDeleteAll) btnCancelDeleteAll.focus();
    });
  }

  if (btnCancelDeleteAll && deleteAllModal) {
    btnCancelDeleteAll.addEventListener("click", () => {
      deleteAllModal.classList.add("hidden");
    });
  }

  if (btnConfirmDeleteAll && deleteAllModal) {
    btnConfirmDeleteAll.addEventListener("click", async () => {
      if (dataError) dataError.classList.add("hidden");
      try {
        await postJson("/api/sessions/delete-all", {});
        deleteAllModal.classList.add("hidden");
        if (dataFeedback) {
          dataFeedback.classList.remove("hidden");
          setTimeout(() => {
            dataFeedback.classList.add("hidden");
          }, 4000);
        }
      } catch (err) {
        console.error("Failed to delete all sessions:", err);
        deleteAllModal.classList.add("hidden");
        if (dataError) {
          dataError.textContent = err.message || "Failed to delete sessions. Please try again.";
          dataError.classList.remove("hidden");
        }
      }
    });
  }
});
