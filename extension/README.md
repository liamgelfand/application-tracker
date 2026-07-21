# Browser Extension - One-Click Job Capture

A small Chrome/Edge (Manifest V3) extension that captures the job listing on the page you're viewing and saves it straight into your Job Application Tracker - no copy/paste.

## How it works

1. On any job listing page, click the extension icon.
2. Click **Capture this page**. The extension grabs the page text (or your current selection) and sends it to your local backend's `/api/parse` endpoint, which uses your active AI provider to extract the company, title, location, salary, etc.
3. Review the parsed fields and click **Save to Tracker**. It's created via `/api/applications`.

## Install (load unpacked)

1. Make sure the tracker backend is running (default `http://localhost:8000`).
2. Open `chrome://extensions` (or `edge://extensions`).
3. Enable **Developer mode** (top right).
4. Click **Load unpacked** and select this `extension/` folder.
5. Pin the extension for easy access.

## Configuration

If your backend runs somewhere other than `http://localhost:8000`, open the extension's **Settings** (right-click the icon -> Options, or the "Settings" link in the popup) and set the backend URL.

## Notes

- Requires an active AI provider configured in the tracker (Settings -> AI Providers), since capture uses the same parsing endpoint as paste-to-add.
- The extension only talks to the backend URL you configure (declared in `host_permissions`). It sends page text there for parsing and nothing else.
- Firefox support: the manifest is standard MV3; minor tweaks may be needed for `about:debugging` loading.
