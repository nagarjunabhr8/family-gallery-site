# CLAUDE.md

Guidance for Claude Code when working in `family-memories/`.

## ABSOLUTE RULES (never break these)

1. **Photo source folders are READ-ONLY.** Never delete, move, rename, overwrite
   or edit any original file. Never write anything (thumbnails, sidecars, temp
   files, `.db`, `Thumbs.db`-style caches) inside a source folder. Open source
   files only in read-binary mode (`"rb"`).
2. **All generated data** (database, thumbnails, face data, cache, logs) goes
   only in the app data folder: `family-memories/data/` by default, overridable
   with the `FM_DATA_DIR` env var. Every write must go through
   `backend/app/safety.py`, which refuses paths outside the data folder.
3. **No cloud uploads.** All processing and AI models run locally. No telemetry,
   no remote APIs, no CDN-hosted models at runtime.
4. **Never delete** photos as a result of dedupe/best-shot logic — only hide or
   rank them in the app's own database.

## What this is

"Family Memories" — local-first family photo/video memories app. Spec and
phase plan live in `README.md`. Build one phase at a time and ask the user to
test after each.

## Stack

- `backend/` — Python 3.12, FastAPI, SQLAlchemy + SQLite, Pillow, pillow-heif,
  OpenCV (headless). Virtualenv at `backend/.venv`.
- `frontend/` — React + TypeScript + Vite + Tailwind v4 + Framer Motion.
- `desktop/` — Tauri 2 wrapper (later; requires Rust, not yet installed).
- Web mode: FastAPI serves `frontend/dist`. Bound to `127.0.0.1` for now;
  LAN + PIN login is a later step.

## Commands (PowerShell)

```powershell
# backend
cd backend
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m app          # serves API + built frontend on http://127.0.0.1:8765
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8765   # dev with autoreload
.\.venv\Scripts\python -m pytest

# prove a photo folder was not modified (run before and after scanning)
.\.venv\Scripts\python ..\scripts\verify_readonly.py snapshot "D:\Photos\Sample"
.\.venv\Scripts\python ..\scripts\verify_readonly.py compare  "D:\Photos\Sample"

# frontend
cd frontend
npm install
npm run dev      # Vite dev server, proxies /api to :8765
npm run build    # output in frontend/dist, served by FastAPI
```

## Tests

```powershell
# everything: pytest (+coverage), frontend build, Playwright E2E
powershell -ExecutionPolicy Bypass -File scripts\test_all.ps1

# backend only
cd backend; .\.venv\Scripts\python -m pytest --cov=app

# E2E only (first time: npm install; npx playwright install chromium)
cd e2e; npx playwright test          # report: npx playwright show-report
$env:FM_E2E_KEEP=1; npx playwright test   # keep the temp world for debugging
```

- E2E runs against a **throwaway world** in the OS temp folder (`fm-e2e-*`):
  generated photos (`scripts/make_sample_photos.py`), fake songs and a fresh
  `FM_DATA_DIR`, with the app on port 8799. Never point tests at real photos
  or `data/`.
- The `read-only proof` project runs last and fails if any byte, size or
  mtime in the sample photo/music folders changed, or any file was added or
  removed. Keep it passing; never weaken it.
- Projects run in order: `desktop` → `phone` (Pixel 7) → `read-only proof`;
  tests share one library, so spec files are numbered and depend on earlier ones.
- Synthetic photos have no faces and the temp data folder has no AI models,
  so people naming/merging is tested in `backend/tests/test_people_api.py`.
