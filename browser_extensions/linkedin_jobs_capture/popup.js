const STORAGE_KEY = "linkedin_jobs_session";
const COUNT_EL = document.getElementById("count");
const STATUS_EL = document.getElementById("status");

const exportCsvBtn = document.getElementById("export-csv");
const exportJsonlBtn = document.getElementById("export-jsonl");
const clearBtn = document.getElementById("clear");
const refreshBtn = document.getElementById("refresh");

exportCsvBtn.addEventListener("click", () => exportSession("csv"));
exportJsonlBtn.addEventListener("click", () => exportSession("jsonl"));
clearBtn.addEventListener("click", clearSession);
refreshBtn.addEventListener("click", refreshCount);

refreshCount();

async function refreshCount() {
  const records = await getSessionRecords();
  COUNT_EL.textContent = String(records.length);
  setStatus(records.length ? `${records.length} record(s) saved.` : "No records saved yet.");
}

async function exportSession(format) {
  const records = await getSessionRecords();
  if (records.length === 0) {
    setStatus("Nothing to export yet.");
    return;
  }
  const timestamp = safeTimestamp(new Date());
  const baseName = `linkedin_jobs_session_${timestamp}`;
  const text = format === "csv" ? toCsv(records) : toJsonl(records);
  const mimeType = format === "csv" ? "text/csv;charset=utf-8" : "application/x-ndjson;charset=utf-8";
  const extension = format === "csv" ? "csv" : "jsonl";
  downloadText(`${baseName}.${extension}`, text, mimeType);
  setStatus(`Exported ${records.length} record(s) as ${extension.toUpperCase()}.`);
}

async function clearSession() {
  await chrome.storage.local.remove(STORAGE_KEY);
  COUNT_EL.textContent = "0";
  setStatus("Session cleared.");
}

async function getSessionRecords() {
  const data = await chrome.storage.local.get(STORAGE_KEY);
  const stored = data[STORAGE_KEY];
  if (Array.isArray(stored)) return stored;
  if (stored && Array.isArray(stored.records)) return stored.records;
  return [];
}

function setStatus(message) { STATUS_EL.textContent = message; }
function safeTimestamp(date) { return date.toISOString().replace(/[:.]/g, "-"); }

function downloadText(filename, text, mimeType) {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function toJsonl(records) { return records.map((record) => JSON.stringify(record)).join("
") + "
"; }

function toCsv(records) {
  const fields = ["source", "capture_method", "saved_at", "captured_at", "source_job_id", "source_url", "title", "company", "location", "posted_text", "description", "page_url", "detail_text", "card_text"];
  const lines = [fields.join(",")];
  for (const record of records) {
    const flat = flattenRecord(record);
    lines.push(fields.map((field) => csvEscape(flat[field] ?? "")).join(","));
  }
  return lines.join("
") + "
";
}

function flattenRecord(record) {
  return { ...record, page_url: record.raw?.page_url || "", detail_text: record.raw?.detail_text || "", card_text: record.raw?.card_text || "" };
}

function csvEscape(value) {
  const stringValue = String(value).replace(/?
/g, " ");
  if (/[",
]/.test(stringValue)) return `"${stringValue.replace(/"/g, '""')}"`;
  return stringValue;
}
