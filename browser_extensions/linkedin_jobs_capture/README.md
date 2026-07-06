# LinkedIn Jobs Local Capture

Chrome/Chromium extension for manually capturing visible LinkedIn Jobs while you browse.

It stores records only in `chrome.storage.local` and exports the current session as CSV or JSONL. The exported file can be uploaded into Job Market Intelligence.

## What it does

- Injects a small floating bar into `https://www.linkedin.com/jobs/*` pages.
- Lets you click `Save visible job` for the currently visible job detail panel.
- Deduplicates jobs within the current local session.
- Exports the session as CSV or JSONL from the popup.
- Clears the local session when you want to start over.

## What it does not do

- No network calls.
- No CRM integration.
- No API credentials.
- No auto-scroll.
- No automated LinkedIn clicking.
- No scraping in the background.

## Install locally

1. Open `chrome://extensions/`.
2. Enable Developer Mode.
3. Click `Load unpacked`.
4. Select this folder:

```text
browser_extensions/linkedin_jobs_capture
```

## Recommended workflow

1. Start the Job Market Intelligence app locally.
2. Open LinkedIn Jobs manually.
3. Open interesting jobs in the detail panel.
4. Click `Save visible job` in the floating bar.
5. Repeat during your search session.
6. Open the extension popup.
7. Export CSV or JSONL.
8. Upload that file in the app UI.

## Exported fields

The extension exports fields such as:

- `source`
- `capture_method`
- `captured_at`
- `saved_at`
- `source_job_id`
- `source_url`
- `title`
- `company`
- `location`
- `posted_text`
- `description`
- `raw.page_url`
- `raw.detail_text`
- `raw.card_text`
