Build a local-first family photo memories app called "Family Memories" that runs
as BOTH a Windows desktop app and a web app (browser, also reachable from phones
on my home Wi-Fi).

ABSOLUTE RULES (put these in CLAUDE.md and follow them always):
- Photo source folders are READ-ONLY. Never delete, move, rename, overwrite or
  edit any original file. Never write anything inside source folders.
- All generated data (thumbnails, database, face data, cache) goes only in the
  app's own data folder.
- No cloud uploads. All processing and AI models run locally.

TECH STACK:
- Backend: Python 3.12 + FastAPI + SQLite (SQLAlchemy). Background job queue for scanning.
- Frontend: React + TypeScript + Vite + Tailwind + Framer Motion.
- Desktop: Tauri 2 wrapping the same frontend, launching the backend as a sidecar.
- Web: same frontend served by FastAPI; bind to LAN with a simple PIN login.

FEATURES (build in this order, one phase at a time, ask me to test after each):
Phase 1 - Scanner & library
- Settings screen where I add one or more photo/video folders (recursive scan).
- Supported: jpg, jpeg, png, heic, webp, mp4, mov.
- Date detection priority: EXIF DateTimeOriginal -> filename patterns
  (IMG-YYYYMMDD-WA####, IMG_YYYYMMDD_HHMMSS, WhatsApp Image YYYY-MM-DD at ...,
  YYYYMMDD) -> file modified time. Store date_source and confidence.
- Incremental re-scan (only new/changed files). Generate thumbnails.
Phase 2 - Duplicates & best shot
- Exact duplicates by SHA-256; near-duplicates by perceptual hash (pHash, Hamming
  distance threshold configurable) and burst grouping (same minute).
- Quality score: sharpness (Laplacian variance), exposure, resolution, face
  quality/eyes open, aesthetic score (CLIP-based). Show only the best per group;
  let me review groups and change the chosen photo. Never delete.
Phase 3 - People
- Local face detection + clustering (InsightFace). UI to name clusters, merge,
  and split. Person page: photos from oldest to newest, with age shown when a
  birth date is entered.
Phase 4 - Events & occasions
- Auto-group events by time gaps (and GPS when available).
- Occasions: family birthdays/anniversaries I enter; Indian festivals by year
  (Diwali, Ganesh Chaturthi, Sankranti, Dussehra, Ugadi, Raksha Bandhan, Holi);
  CLIP zero-shot scene tags (birthday, wedding, temple, school, travel, beach).
- I can rename, edit, merge events and add custom events.
- Each event shows 1 hero photo + a curated set (max ~12) of the best unique shots.
Phase 5 - Beautiful experience
- Home: "Our Story" life timeline from oldest to latest, grouped by year and
  life stage (childhood, school, college, marriage, kids...).
- "Best of each year", "On this day", slideshow with music, fullscreen viewer.
- Warm, elegant design: soft neutral palette, serif headings, large photos,
  smooth transitions, dark mode, responsive for phone.
Phase 6 - Quality
- Unit tests (pytest) for date parsing, hashing, dedupe; Playwright E2E tests
  for main flows. A test run must prove that source files are unchanged
  (compare hashes before/after scan).

Start by proposing the folder structure and data model, then build Phase 1.
Use a small sample folder for testing before I point it at my real photos.