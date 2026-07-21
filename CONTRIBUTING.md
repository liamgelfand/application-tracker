# Contributing

Thanks for your interest in improving Job Application Tracker! Contributions of all kinds are welcome: bug reports, feature ideas, docs, and code.

## Getting set up

See the [README](README.md) for full setup. In short:

```bash
make setup   # install backend + frontend dependencies
make dev     # run both servers
```

- Backend: Python + FastAPI in `backend/`
- Frontend: React + TypeScript (Vite) in `frontend/`

## Development workflow

1. Fork the repo and create a branch: `git checkout -b feat/my-change`.
2. Make your change. Keep the scope focused.
3. Make sure it builds and imports cleanly (this is what CI checks):
   - Backend: `cd backend && python -m compileall app && python -c "from app.main import app"`
   - Frontend: `cd frontend && npm run build`
4. Commit with a clear message (see below) and open a pull request.

## Commit messages

We loosely follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: ...` a new feature
- `fix: ...` a bug fix
- `docs: ...` documentation only
- `refactor: ...`, `chore: ...`, `test: ...`

## Guidelines

- Never commit secrets. API keys and email passwords live in the local SQLite DB (`data/`), which is gitignored. Double-check `git status` before committing.
- Keep the app runnable with zero paid services (SQLite + optional local Ollama).
- Prefer small, reviewable PRs.

## Reporting bugs / requesting features

Please use the issue templates. Include steps to reproduce for bugs, and the "why" for feature requests.
