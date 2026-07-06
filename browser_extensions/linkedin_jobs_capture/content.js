const STORAGE_KEY = "linkedin_jobs_session";
const BAR_ID = "hermes-linkedin-capture-bar";
const STATUS_ID = "hermes-linkedin-capture-status";
const COUNT_ID = "hermes-linkedin-capture-count";
const SAVE_ID = "hermes-linkedin-capture-save";
const CLEAR_ID = "hermes-linkedin-capture-clear";

if (!window.__hermesLinkedInCaptureInstalled) {
  window.__hermesLinkedInCaptureInstalled = true;
  injectCaptureBarWhenReady();
  chrome.storage.onChanged.addListener((changes, areaName) => {
    if (areaName === "local" && changes[STORAGE_KEY]) {
      updateCountLabel();
    }
  });
}

async function injectCaptureBarWhenReady() {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectCaptureBar, { once: true });
  } else {
    injectCaptureBar();
  }
}

function injectCaptureBar() {
  if (document.getElementById(BAR_ID)) {
    updateCountLabel();
    return;
  }

  const style = document.createElement("style");
  style.textContent = `
    #${BAR_ID} {
      position: fixed;
      right: 16px;
      bottom: 16px;
      z-index: 2147483647;
      width: 272px;
      background: rgba(17, 24, 39, 0.96);
      color: #f9fafb;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 14px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.35);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }

    #${BAR_ID} * {
      box-sizing: border-box;
    }

    #${BAR_ID} .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px 8px;
      background: rgba(10, 102, 194, 0.16);
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }

    #${BAR_ID} .title {
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }

    #${BAR_ID} .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 28px;
      height: 22px;
      padding: 0 8px;
      border-radius: 999px;
      background: #0a66c2;
      color: white;
      font-size: 12px;
      font-weight: 700;
    }

    #${BAR_ID} .body {
      padding: 10px 12px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    #${BAR_ID} .actions {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }

    #${BAR_ID} button {
      border: 0;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      color: white;
      transition: transform 0.08s ease, filter 0.08s ease;
    }

    #${BAR_ID} button:hover { filter: brightness(1.05); }
    #${BAR_ID} button:active { transform: translateY(1px); }
    #${SAVE_ID} { background: #0a66c2; }
    #${CLEAR_ID} { background: #dc2626; }

    #${BAR_ID} .hint {
      font-size: 11px;
      line-height: 1.35;
      color: rgba(249,250,251,0.72);
    }

    #${STATUS_ID} {
      font-size: 11px;
      line-height: 1.35;
      color: rgba(249,250,251,0.84);
      min-height: 2.7em;
      white-space: pre-wrap;
    }

    #${BAR_ID} .footer {
      padding: 0 12px 12px;
      font-size: 10px;
      color: rgba(249,250,251,0.58);
    }
  `;
  document.documentElement.appendChild(style);

  const root = document.createElement("div");
  root.id = BAR_ID;
  root.innerHTML = `
    <div class="header">
      <div class="title">LinkedIn Jobs Capture</div>
      <div class="badge" id="${COUNT_ID}">0</div>
    </div>
    <div class="body">
      <div class="actions">
        <button id="${SAVE_ID}">Save visible job</button>
        <button id="${CLEAR_ID}">Clear session</button>
      </div>
      <div class="hint">Save visible jobs locally, then export CSV/JSONL from the extension popup.</div>
      <div id="${STATUS_ID}">Ready to capture.</div>
    </div>
    <div class="footer">No network calls · No auto-scroll · Manual capture only</div>
  `;
  document.documentElement.appendChild(root);

  root.querySelector(`#${SAVE_ID}`).addEventListener("click", saveVisibleJob);
  root.querySelector(`#${CLEAR_ID}`).addEventListener("click", clearSession);

  updateCountLabel();
  setBarStatus("Capture bar ready.");
}

async function saveVisibleJob() {
  try {
    const record = captureVisibleLinkedInJob();
    if (!record || record.error) {
      setBarStatus(record?.error || "Could not capture the visible job.");
      return;
    }

    const session = await getSession();
    const dedupeKey = record.source_job_id || record.source_url || `${record.title}|${record.company}|${record.location}`;
    const exists = session.records.some((item) => {
      const key = item.source_job_id || item.source_url || `${item.title}|${item.company}|${item.location}`;
      return key === dedupeKey;
    });

    if (exists) {
      setBarStatus("That job is already saved in this session.");
      return;
    }

    session.records.push({
      ...record,
      saved_at: new Date().toISOString(),
    });

    await setSession(session);
    updateCountLabel(session.records.length);
    setBarStatus(`Saved: ${record.title || "untitled job"}.`);
  } catch (error) {
    setBarStatus(`Save error: ${error?.message || String(error)}`);
  }
}

async function clearSession() {
  try {
    await chrome.storage.local.remove(STORAGE_KEY);
    updateCountLabel(0);
    setBarStatus("Sesión limpia.");
  } catch (error) {
    setBarStatus(`No pude limpiar la sesión: ${error?.message || String(error)}`);
  }
}

async function updateCountLabel(forcedCount = null) {
  const el = document.getElementById(COUNT_ID);
  if (!el) return;

  if (typeof forcedCount === "number") {
    el.textContent = String(forcedCount);
    return;
  }

  const session = await getSession();
  el.textContent = String(session.records.length);
}

function setBarStatus(message) {
  const el = document.getElementById(STATUS_ID);
  if (el) el.textContent = message;
}

async function getSession() {
  const data = await chrome.storage.local.get(STORAGE_KEY);
  if (!data[STORAGE_KEY] || !Array.isArray(data[STORAGE_KEY].records)) {
    return { version: 1, records: [] };
  }
  return data[STORAGE_KEY];
}

async function setSession(session) {
  await chrome.storage.local.set({
    [STORAGE_KEY]: {
      version: 1,
      updated_at: new Date().toISOString(),
      records: session.records,
    },
  });
}

function captureVisibleLinkedInJob() {
  const capturedAt = new Date().toISOString();
  const pageUrl = window.location.href;

  if (!location.hostname.includes("linkedin.com")) {
    return { error: "Esta extensión está pensada para usarse en linkedin.com/jobs." };
  }

  const detailRecord = extractVisibleDetailRecord(capturedAt, pageUrl);
  if (detailRecord) return detailRecord;

  const selectedCard = findSelectedJobCard();
  if (selectedCard) {
    const cardRecord = extractJobFromCard(selectedCard, capturedAt, pageUrl);
    if (cardRecord) return cardRecord;
  }

  const fallbackCards = getVisibleJobCards();
  for (const card of fallbackCards) {
    const record = extractJobFromCard(card, capturedAt, pageUrl);
    if (record) return record;
  }

  return {
    error: "No encontré un empleo visible. Asegúrate de abrir un job y dejarlo cargado en la vista actual.",
  };
}

function extractJobFromCard(card, capturedAt, pageUrlValue) {
  if (!card) return null;

  const linkElement = firstMatch(card, [
    "a[href*='/jobs/view/']",
    "a.job-card-list__title",
    "a.job-card-container__link",
    "a[aria-label*='job']",
  ]);

  const sourceUrl = normalizeLinkedInJobUrl(linkElement?.href || card.querySelector("a")?.href || "");
  const sourceJobId = extractLinkedInJobId(sourceUrl)
    || card.getAttribute?.("data-job-id")
    || card.getAttribute?.("data-occludable-job-id")
    || "";

  const title = cleanText(textFromFirst(card, [
    ".job-card-list__title",
    ".job-card-container__link strong",
    ".job-details-jobs-unified-top-card__job-title",
    ".jobs-unified-top-card__job-title",
    "h1",
    "a[href*='/jobs/view/'] strong",
    "a[href*='/jobs/view/']",
    "strong",
  ]));

  const company = cleanText(textFromFirst(card, [
    ".job-card-container__primary-description",
    ".job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name",
    ".artdeco-entity-lockup__subtitle",
    "[class*='primary-description']",
  ]));

  const locationText = cleanText(textFromFirst(card, [
    ".job-card-container__metadata-item",
    ".job-details-jobs-unified-top-card__primary-description-container",
    ".jobs-unified-top-card__bullet",
    ".jobs-unified-top-card__subtitle-primary-grouping",
    ".artdeco-entity-lockup__caption",
    "[class*='metadata-item']",
  ]));

  const postedText = cleanText(textFromFirst(card, [
    "time",
    ".job-card-container__footer-item",
    ".job-details-jobs-unified-top-card__tertiary-description-container",
    "[class*='listed-time']",
  ]));

  const description = cleanText(textFromFirst(card, [
    ".jobs-description__content",
    "#job-details",
    ".jobs-box__html-content",
  ]));

  if (!title && !company && !sourceUrl && !description) {
    return null;
  }

  return {
    source: "linkedin_jobs",
    capture_method: description ? "browser_extension_visible_detail" : "browser_extension_visible_cards",
    captured_at: capturedAt,
    source_url: sourceUrl || pageUrlValue,
    source_job_id: sourceJobId,
    title,
    company,
    location: locationText,
    posted_text: postedText,
    description,
    raw: {
      page_url: pageUrlValue,
      card_text: cleanText(card.innerText || card.textContent || "").slice(0, 5000),
    },
  };
}

function extractVisibleDetailRecord(capturedAt, pageUrlValue) {
  const detailRoot = document.querySelector(".jobs-search__job-details--container")
    || document.querySelector(".jobs-details")
    || document.querySelector("main")
    || document.body;

  const title = cleanText(textFromFirst(document, [
    ".job-details-jobs-unified-top-card__job-title a",
    ".job-details-jobs-unified-top-card__job-title",
    ".jobs-unified-top-card__job-title",
    "h1",
  ]));

  const company = cleanText(textFromFirst(document, [
    ".job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name",
    ".job-details-jobs-unified-top-card__primary-description-container a",
  ]));

  const locationText = cleanText(textFromFirst(document, [
    ".job-details-jobs-unified-top-card__primary-description-container",
    ".jobs-unified-top-card__bullet",
    ".jobs-unified-top-card__subtitle-primary-grouping",
  ]));

  const postedText = cleanText(textFromFirst(document, [
    ".job-details-jobs-unified-top-card__tertiary-description-container",
    ".jobs-unified-top-card__subtitle-primary-grouping time",
    "time",
  ]));

  const description = cleanText(textFromFirst(detailRoot, [
    ".jobs-description__content",
    "#job-details",
    ".jobs-box__html-content",
  ]));

  const detailLink = firstMatch(document, [
    ".job-details-jobs-unified-top-card__job-title a[href*='/jobs/view/']",
    ".job-details-jobs-unified-top-card__primary-description-container a[href*='/jobs/view/']",
    "a[href*='/jobs/view/']",
  ]);

  const sourceUrl = normalizeLinkedInJobUrl(detailLink?.href || pageUrlValue);
  const sourceJobId = extractLinkedInJobId(sourceUrl) || extractLinkedInJobId(pageUrlValue);

  if (!title && !company && !description) {
    return null;
  }

  return {
    source: "linkedin_jobs",
    capture_method: "browser_extension_visible_detail",
    captured_at: capturedAt,
    source_url: sourceUrl,
    source_job_id: sourceJobId,
    title,
    company,
    location: locationText,
    posted_text: postedText,
    description,
    raw: {
      page_url: pageUrlValue,
      detail_text: cleanText(detailRoot.innerText || detailRoot.textContent || "").slice(0, 8000),
    },
  };
}

function findSelectedJobCard() {
  const selectors = [
    ".job-card-container--clickable[aria-current='true']",
    ".job-card-container--clickable[aria-selected='true']",
    ".job-card-container--clickable[aria-pressed='true']",
    ".job-card-container.is-active",
    "li[data-occludable-job-id][aria-current='true']",
    "li[data-occludable-job-id][aria-selected='true']",
    "[data-job-id][aria-current='true']",
    "[data-job-id][aria-selected='true']",
  ];

  for (const selector of selectors) {
    const node = document.querySelector(selector);
    if (node) return node;
  }
  return null;
}

function getVisibleJobCards() {
  const selectors = [
    ".job-card-container",
    "li[data-occludable-job-id]",
    "li.jobs-search-results__list-item",
    "[data-job-id]",
    "article[data-job-id]",
  ];

  const elements = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
  return uniqueVisibleElements(elements);
}

function uniqueVisibleElements(elements) {
  const seen = new Set();
  const result = [];
  for (const element of elements) {
    if (!element || seen.has(element)) continue;
    seen.add(element);
    result.push(element);
  }
  return result.filter(isVisible);
}

function isVisible(element) {
  if (!element || !(element instanceof Element)) return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function firstMatch(root, selectors) {
  for (const selector of selectors) {
    const element = root.querySelector(selector);
    if (element) return element;
  }
  return null;
}

function textFromFirst(root, selectors) {
  const element = firstMatch(root, selectors);
  return element ? element.innerText || element.textContent || "" : "";
}

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function normalizeLinkedInJobUrl(url) {
  if (!url) return "";
  try {
    const parsed = new URL(url, window.location.origin);
    const match = parsed.pathname.match(/\/jobs\/view\/(\d+)/);
    if (match) return `https://www.linkedin.com/jobs/view/${match[1]}/`;
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return url.split("?")[0];
  }
}

function extractLinkedInJobId(url) {
  const match = String(url || "").match(/\/jobs\/view\/(\d+)/);
  return match ? match[1] : "";
}
