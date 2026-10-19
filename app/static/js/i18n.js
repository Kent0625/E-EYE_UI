// Client-side i18n loader and reactive string replacer
let currentDictionary = {};
let currentLang = localStorage.getItem("eeye_lang") || "en";

export async function initI18n() {
  await setLanguage(currentLang);
  
  // Wire language toggle buttons if present
  document.querySelectorAll(".lang-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const selected = e.currentTarget.getAttribute("data-lang");
      if (selected && selected !== currentLang) {
        setLanguage(selected);
      }
    });
  });
}

export async function setLanguage(lang) {
  try {
    const res = await fetch(`/static/i18n/${lang}.json`);
    if (!res.ok) throw new Error(`Could not load ${lang}.json`);
    currentDictionary = await res.json();
    currentLang = lang;
    localStorage.setItem("eeye_lang", lang);
    document.cookie = `eeye_lang=${lang}; path=/; max-age=31536000; SameSite=Lax`;
    document.documentElement.lang = lang;
    
    // Update active button state
    document.querySelectorAll(".lang-btn").forEach(btn => {
      if (btn.getAttribute("data-lang") === lang) {
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
      } else {
        btn.classList.remove("active");
        btn.setAttribute("aria-pressed", "false");
      }
    });
    
    applyTranslations();
  } catch (err) {
    console.error("i18n initialization error:", err);
  }
}

export function t(key, params = {}) {
  let str = currentDictionary[key] || key;
  for (const [k, v] of Object.entries(params)) {
    str = str.replace(new RegExp(`\\{${k}\\}`, "g"), v);
  }
  return str;
}

export function applyTranslations(root = document) {
  root.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const translated = t(key);
    if (el.tagName === "INPUT" && el.hasAttribute("placeholder")) {
      el.placeholder = translated;
    } else {
      el.textContent = translated;
    }
  });

  root.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    el.title = t(key);
  });

  root.querySelectorAll("[data-i18n-aria]").forEach(el => {
    const key = el.getAttribute("data-i18n-aria");
    el.setAttribute("aria-label", t(key));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initI18n();
});
