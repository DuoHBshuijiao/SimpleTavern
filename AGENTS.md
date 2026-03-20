# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

SimpleTavern is a local single-user AI character roleplay chat application. Frontend is Vue 3 (Vite + TypeScript), backend is Python FastAPI. Data is stored as local JSON files under `data/` (no database). See `README.md` for full details.

### Services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| Backend (FastAPI) | `cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` | 8000 | Must activate venv first: `source /workspace/venv/bin/activate` |
| Frontend (Vite dev) | `cd frontend && npm run dev -- --host 0.0.0.0` | 5173 | Proxies `/api` requests to backend via `vite.config.ts` |

Both services must run for the application to work. Start the backend before the frontend.

### Lint / Build / Test

- **Type check + build**: `cd frontend && npm run build` (runs `vue-tsc -b && vite build`)
- **No ESLint** configured in this project.
- **No automated tests** exist in this project (no test files or test framework).
- **Python backend** has no linter or test framework configured.

### Non-obvious caveats

- The Python venv must be created at `/workspace/venv` (the deploy script and README both expect this location).
- `python3.12-venv` system package is required to create the venv on Ubuntu 24.04 (not installed by default).
- The backend working directory must be `/workspace/backend` when starting uvicorn, as it uses relative imports (`app.main:app`).
- AI chat features require a user-configured OpenAI-compatible API key/URL in the Settings panel; the app boots and serves the UI without it, but chat generation won't work.
- The frontend `npm run preview` (port 4173) serves the production build; use `npm run dev` (port 5173) for development with HMR.
- Health check endpoint: `GET /api/health` returns `{"ok": true}`.
