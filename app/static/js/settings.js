// Client-side interactions for Settings Screen
import { getJson, postJson } from "./api.js";
import { t, setLanguage } from "./i18n.js";

document.addEventListener("DOMContentLoaded", () => {
  // 1. Site Name Saving
  const btnSaveSite = document.getElementById("btn-save-site");
  const siteInput = document.getElementById("setting-site-name");
  const siteFeedback = document.getElementById("site-save-feedback");

  if (btnSaveSite && siteInput) {
    btnSaveSite.addEventListener("click", async () => {
      const siteName = siteInput.value.trim();
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
      }
    });
  }

  // 2. Clock Synchronization
  const btnSyncClock = document.getElementById("btn-sync-clock");
  const clockWarning = document.getElementById("clock-warning");
  const clockFeedback = document.getElementById("clock-sync-feedback");

  if (btnSyncClock) {
    btnSyncClock.addEventListener("click", async () => {
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
  if (researchToggle) {
    researchToggle.addEventListener("change", async (e) => {
      const isChecked = e.target.checked;
      try {
        await postJson("/api/settings", { research_mode: isChecked ? "1" : "0" });
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

  if (btnDeleteAll && deleteAllModal) {
    btnDeleteAll.addEventListener("click", () => {
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
      }
    });
  }
});
