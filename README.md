# Job Application Tracker

A self-hosted, open-source app for tracking your job applications end to end. It parses pasted job listings with AI, monitors your email inbox for application-related messages, and keeps every application organized on a kanban board with a full status timeline.

Everything runs locally on your machine. Bring your own AI provider (OpenAI, Anthropic, Google Gemini, or a local Ollama model) and your own email account. No accounts, no servers, no cost.

## Features

- **Kanban board + table** to track applications across stages: Saved, Applied, Phone Screen, Interview, Offer, Rejected, Ghosted, Accepted.
- **Paste-to-add**: paste any job listing and an LLM extracts the company, title, location, salary, URL, skills, and a summary. Review, then save.
- **Inbox monitoring (IMAP)**: connect any email provider. A background job reads new mail, detects job-related messages (confirmations, recruiter outreach, interview invites, rejections), matches them to your applications, and proposes updates.
- **Review queue**: proposed changes wait for your approval by default (flip on auto-apply if you trust it).
- **Multiple AI providers, toggleable**: configure several providers with their own keys and models, and switch the active one anytime. Local models via Ollama are fully supported.
- **Per-application timeline** recording every status change and email event.
- **Secrets encrypted at rest**: API keys and email passwords are encrypted with a locally generated key.

## Tech stack

- **Backend**: Python, FastAPI, SQLAlchemy, SQLite, APScheduler, LiteLLM (unified LLM interface).
- **Frontend**: React, TypeScript, Vite, TanStack Query.

## Architecture

```
frontend (React)  ->  backend (FastAPI)  ->  SQLite
                             |-> LLM layer (LiteLLM) -> OpenAI / Anthropic / Gemini / Ollama
                             |-> IMAP poller (APScheduler) -> your inbox -> review queue
```

## Quickstart

### Option A: Docker (recommended)

Requires Docker + Docker Compose.

```bash
git clone <your-repo-url> application-tracker
cd application-tracker
docker compose up --build
```

Then open http://localhost:8080.

### Option B: Make (local dev)

Requires Python 3.11+, Node 18+, and `make`. (macOS/Linux have `make` built in; on Windows install it via `choco install make`, `winget install GnuWin32.Make`, or use WSL.)

```bash
git clone <your-repo-url> application-tracker
cd application-tracker
make setup    # installs backend + frontend dependencies (run once)
make dev      # runs the backend and frontend together
```

Then open http://localhost:5173. Run `make help` to see all available commands.

### Option C: Manual

```bash
# Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api` to the backend on port 8000.

## First-time setup

1. Open the app and go to **Settings**.
2. Under **AI Providers**, add a provider:
   - **OpenAI / Anthropic / Gemini**: pick a model and paste your API key.
   - **Ollama**: no key needed. Install [Ollama](https://ollama.com), run `ollama pull llama3.1`, and make sure it's running at `http://localhost:11434`.
   - You can add several and use **Set Active** to switch between them anytime.
3. (Optional) Under **Monitored Inboxes**, add an IMAP account and click **Test Connection**.
   - For Gmail/Outlook, create an **app password** (not your normal password) and use that.
   - Common IMAP hosts: `imap.gmail.com` (993), `outlook.office365.com` (993).
4. Go to **Add Application**, paste a job listing, and click **Parse with AI**.

## Configuration

Backend settings are read from environment variables or a `backend/.env` file (see `backend/.env.example`):

| Variable | Default | Description |
| --- | --- | --- |
| `DATA_DIR` | `./data` | Where the SQLite DB and encryption key live. |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed CORS origin. |
| `EMAIL_POLL_INTERVAL_SECONDS` | `300` | How often inboxes are polled. |
| `APP_SECRET_KEY` | auto-generated | Override the encryption key (base64 urlsafe, 32 bytes). |

## Security notes

- This is a **single-user, local-first** app with no authentication by default. Don't expose it directly to the public internet without adding auth and TLS.
- API keys and email passwords are encrypted at rest using a key stored in `DATA_DIR/secret.key`. Keep that file (and your `data/` directory) private and backed up. If you lose the key, stored secrets can't be decrypted.
- Your email/API credentials never leave your machine except to talk to the providers you configure.

## API

Interactive API docs are available at http://localhost:8000/docs when the backend is running.

## Roadmap / ideas

- Browser extension / bookmarklet to capture the current job page in one click.
- Analytics: application funnel, response rate, time-to-response.
- Follow-up reminders and interview calendar (.ics) export.
- CSV / JSON import and export.
- Resume-tailoring suggestions per listing.
- Optional authentication for hosted deployments.

## Contributing

Issues and pull requests are welcome. This project is intentionally simple to fork and extend.

## License

MIT. See [LICENSE](LICENSE).
