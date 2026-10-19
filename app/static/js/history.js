// Client-side interactions for History Screen
import { getJson, deleteJson } from "./api.js";
import { t } from "./i18n.js";

let activeFilter = "all";
let sessionToDelete = null;
let currentSessions = [];

function formatEyeSummary(eyes) {
  if (!eyes) return { od: "OD: --", os: "OS: --" };
  const formatSe = (eye) => {
    if (!eye || eye.status !== "ok" || eye.se_D === undefined || eye.se_D === null) {
      if (eye && eye.status === "retake_needed") return "Retake";
      return "--";
    }
    const val = Number(eye.se_D);
    const sign = val < 0 ? "\u2212" : (val > 0 ? "+" : "");
    return `${sign}${Math.abs(val).toFixed(2)} D`;
  };
  return {
    od: `OD: ${formatSe(eyes.OD)}`,
    os: `OS: ${formatSe(eyes.OS)}`
  };
}

function formatDate(isoStr) {
  if (!isoStr) return "";
  try {
    return isoStr.substring(0, 16).replace("T", " ");
  } catch (e) {
    return isoStr;
  }
}

export async function loadHistory() {
  const searchInput = document.getElementById("history-search");
  const listContainer = document.getElementById("session-list");
  if (!listContainer) return;

  const q = searchInput ? searchInput.value.trim() : "";
  try {
    const sessions = await getJson(`/api/sessions?q=${encodeURIComponent(q)}&filter=${encodeURIComponent(activeFilter)}`);
    currentSessions = sessions || [];
    renderSessions(currentSessions, q);
  } catch (err) {
    console.error("Failed to load sessions:", err);
  }
}

function renderSessions(sessions, searchQuery) {
  const listContainer = document.getElementById("session-list");
  if (!listContainer) return;

  if (!sessions || sessions.length === 0) {
    if (searchQuery || activeFilter !== "all") {
      listContainer.innerHTML = `
        <div class="history-empty-card" id="history-no-match-card">
          <h3 class="history-empty-title" data-i18n="history.noMatchTitle">${t("history.noMatchTitle")}</h3>
          <p class="history-empty-desc" data-i18n="history.noMatchDesc">${t("history.noMatchDesc")}</p>
          <button type="button" id="btn-clear-search" class="btn btn-secondary" data-i18n="history.clearSearch">${t("history.clearSearch")}</button>
        </div>
      `;
      const clearBtn = document.getElementById("btn-clear-search");
      if (clearBtn) {
        clearBtn.addEventListener("click", () => {
          const searchInput = document.getElementById("history-search");
          if (searchInput) searchInput.value = "";
          activeFilter = "all";
          updateFilterButtons();
          loadHistory();
        });
      }
    } else {
      listContainer.innerHTML = `
        <div class="history-empty-card" id="history-empty-card">
          <h3 class="history-empty-title" data-i18n="history.emptyTitle">${t("history.emptyTitle")}</h3>
          <p class="history-empty-desc" data-i18n="history.emptyDesc">${t("history.emptyDesc")}</p>
          <a href="/screen/new" class="btn btn-primary" data-i18n="history.startScreening">${t("history.startScreening")}</a>
        </div>
      `;
    }
    clearDetailPanel();
    return;
  }

  listContainer.innerHTML = sessions.map(s => {
    const isRefer = s.referral === true;
    const isNoRefer = s.referral === false;
    const badgeClass = isRefer ? "badge-warn" : (isNoRefer ? "badge-ok" : "badge-warn");
    const badgeText = isRefer ? t("result.refer") : (isNoRefer ? t("result.noRefer") : t("result.incomplete"));
    const iconId = isRefer ? "#icon-alert-triangle" : (isNoRefer ? "#icon-check" : "#icon-alert-triangle");
    
    const eyeSummary = formatEyeSummary(s.eyes);
    const dateFormatted = formatDate(s.created_at);
    const siteText = s.site ? ` • ${s.site}` : "";

    return `
      <div class="history-item-card" data-id="${s.id}" data-href="/screen/${s.id}/result" role="button" tabindex="0">
        <div class="history-item-top">
          <span class="history-code numeric">${s.participant_code}</span>
          <span class="badge ${badgeClass}">
            <svg class="icon"><use href="${iconId}"></use></svg>
            <span>${badgeText}</span>
          </span>
        </div>
        <div class="history-meta-row numeric">
          <span>${dateFormatted}${siteText}</span>
        </div>
        <div class="history-eyes-summary">
          <span>${eyeSummary.od}</span>
          <span>${eyeSummary.os}</span>
        </div>
        <div class="history-item-actions">
          <button type="button" class="history-delete-btn" data-id="${s.id}" data-code="${s.participant_code}" aria-label="Delete session ${s.participant_code}">
            <svg class="icon"><use href="#icon-trash-2"></use></svg>
          </button>
        </div>
      </div>
    `;
  }).join("");

  attachItemEvents();
}

function updateFilterButtons() {
  document.querySelectorAll(".filter-btn").forEach(btn => {
    if (btn.getAttribute("data-filter") === activeFilter) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

function attachItemEvents() {
  const cards = document.querySelectorAll(".history-item-card");
  cards.forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".history-delete-btn")) return;
      const sessionId = card.getAttribute("data-id");
      const href = card.getAttribute("data-href");
      if (window.innerWidth >= 1024) {
        cards.forEach(c => c.classList.remove("selected"));
        card.classList.add("selected");
        showDetailPanel(sessionId);
      } else {
        window.location.href = href;
      }
    });

    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        if (e.target.closest(".history-delete-btn")) return;
        e.preventDefault();
        const href = card.getAttribute("data-href");
        window.location.href = href;
      }
    });
  });

  const deleteBtns = document.querySelectorAll(".history-delete-btn");
  deleteBtns.forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      sessionToDelete = {
        id: btn.getAttribute("data-id"),
        code: btn.getAttribute("data-code")
      };
      const modal = document.getElementById("delete-modal");
      if (modal) {
        modal.classList.remove("hidden");
        const cancelBtn = document.getElementById("btn-cancel-delete");
        if (cancelBtn) cancelBtn.focus();
      }
    });
  });

  // If on desktop and nothing selected, select first card
  if (window.innerWidth >= 1024 && cards.length > 0) {
    const firstCard = cards[0];
    firstCard.classList.add("selected");
    showDetailPanel(firstCard.getAttribute("data-id"));
  }
}

function showDetailPanel(sessionId) {
  const detailPanel = document.getElementById("history-detail-panel");
  if (!detailPanel) return;

  const session = currentSessions.find(s => s.id === sessionId);
  if (!session) return;

  const isRefer = session.referral === true;
  const isNoRefer = session.referral === false;
  const bannerClass = isRefer ? "referral-banner-refer" : (isNoRefer ? "referral-banner-norefer" : "referral-banner-refer");
  const bannerIcon = isRefer ? "#icon-alert-triangle" : (isNoRefer ? "#icon-check" : "#icon-alert-triangle");
  const bannerTitle = isRefer ? t("result.refer") : (isNoRefer ? t("result.noRefer") : t("result.incomplete"));

  const eyes = session.eyes || {};
  const formatSeVal = (eye) => {
    if (!eye || eye.status !== "ok" || eye.se_D === undefined || eye.se_D === null) return "--";
    const v = Number(eye.se_D);
    const sign = v < 0 ? "\u2212" : (v > 0 ? "+" : "");
    return `${sign}${Math.abs(v).toFixed(2)} D`;
  };

  detailPanel.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">
          <svg class="icon icon-teal"><use href="#icon-file-text"></use></svg>
          <span class="numeric">${session.participant_code}</span>
        </h3>
        <span class="numeric detail-meta-date">${formatDate(session.created_at)}</span>
      </div>
      <div class="referral-banner ${bannerClass} detail-banner">
        <svg class="banner-icon"><use href="${bannerIcon}"></use></svg>
        <div class="banner-text">
          <div class="banner-title">${bannerTitle}</div>
        </div>
      </div>
      <div class="history-detail-grid">
        <div class="detail-eye-box">
          <div class="detail-eye-label">Right Eye (OD)</div>
          <div class="detail-eye-val numeric">${formatSeVal(eyes.OD)}</div>
        </div>
        <div class="detail-eye-box">
          <div class="detail-eye-label">Left Eye (OS)</div>
          <div class="detail-eye-val numeric">${formatSeVal(eyes.OS)}</div>
        </div>
      </div>
      <div class="detail-actions">
        <a href="/screen/${session.id}/result" class="btn btn-primary btn-block">Open full result screen</a>
      </div>
    </div>
  `;
}

function clearDetailPanel() {
  const detailPanel = document.getElementById("history-detail-panel");
  if (detailPanel) {
    detailPanel.innerHTML = `
      <div class="card history-detail-placeholder">
        <p class="detail-placeholder-text">Select a session to view details.</p>
      </div>
    `;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("history-search");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      loadHistory();
    });
  }

  const filterBtns = document.querySelectorAll(".filter-btn");
  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      activeFilter = btn.getAttribute("data-filter") || "all";
      updateFilterButtons();
      loadHistory();
    });
  });

  const deleteModal = document.getElementById("delete-modal");
  const cancelDeleteBtn = document.getElementById("btn-cancel-delete");
  const confirmDeleteBtn = document.getElementById("btn-confirm-delete");

  if (cancelDeleteBtn && deleteModal) {
    cancelDeleteBtn.addEventListener("click", () => {
      deleteModal.classList.add("hidden");
      sessionToDelete = null;
    });
  }

  if (confirmDeleteBtn && deleteModal) {
    confirmDeleteBtn.addEventListener("click", async () => {
      if (!sessionToDelete) return;
      try {
        await deleteJson(`/api/sessions/${sessionToDelete.id}`);
        deleteModal.classList.add("hidden");
        sessionToDelete = null;
        loadHistory();
      } catch (err) {
        console.error("Delete failed:", err);
      }
    });
  }

  loadHistory();
});
