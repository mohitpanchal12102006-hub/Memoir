# Memoir

Lossless chronology and Google Takeout organizer. Memoir reads huge Takeout archives (ZIP parts) and folders in
place, finds the real capture date of every photo and video, lets you fix doubtful dates, removes duplicates safely,
and writes an organized archive with **no re-compression**: pictures and video streams are copied bit for bit; only
the date metadata and the file times change.

Everything runs on your computer. Nothing is uploaded anywhere.

## Quick start

1. Install **Python 3.10+** (python.org) and **ExifTool** (see `tools/README.txt`).
2. Start Memoir
   - Windows: double-click `run.bat`
   - macOS / Linux: `./run.sh`

   The first start creates a private Python environment and needs internet once. Your browser opens at
   http://127.0.0.1:8787.
3. Follow `docs/USER_GUIDE.md` (add ZIP parts, scan, review, remove duplicates, export).

Optional: install **ffmpeg** to get preview pictures for videos (MKV, AVI, MOV...).

## What it does

- **Reads in place.** ZIP parts are never extracted. Each file is streamed once; only one file at a time is staged temporarily.
- **Smart dates.** Embedded date (EXIF, XMP, QuickTime) first, then Google's JSON sidecar, then the file name
  (Android, Pixel, WhatsApp, Screenshots, Telegram, Snapchat, Instagram, epoch names).
- **Takeout aware.** Sidecars are matched across ZIP parts, including truncated names, numbered copies, `-edited` photos
  and the newer `.supplemental-metadata.json`. Missing parts are detected. Live Photos are paired.
- **Review queue.** Missing, doubtful or damaged dates are flagged. Fix one or many at once (set, shift, space apart), with undo.
- **Duplicates.** Exact (SHA-256) and similar images. Every removal shows the folder it comes from. Default is non-destructive.
- **Lossless export** to a folder or one ZIP: capture date written into every file, file times set, optional
  `YYYY/MM` folders and date-prefixed names. Streams file by file, verifies checksums, can resume after an interruption.
- **Drive aware.** ZIP parts may be on the laptop or an external drive. A disconnected drive pauses the job; reconnect and press Resume.

## Safety

- Sources are opened read-only and are never changed, moved or deleted.
- Removing duplicates only leaves them out of the export (default) or moves loose files to a quarantine folder. Deleting is not offered.
- The server only answers requests from your own computer (it checks Host and Origin headers).

## Your own photos in the interface

Drop `hero.jpg` and `banner.jpg` into `engine/memoir_engine/static/img/` (or `web/public/img/` before building).
Until then the interface shows drawn landscapes.

## Where things are stored

`%USERPROFILE%\.memoir` (Windows) or `~/.memoir`: the catalog database, thumbnail cache (capped at 1 GB), reports
(duplicate removals and exports as CSV) and temp files. Set `MEMOIR_HOME` to move it, `MEMOIR_TMP` to stage temp files on another drive,
`MEMOIR_THUMB_CACHE_MB` to change the cache size.

## Repository map

```
run.bat / run.sh        start the app
engine/                 Python engine: scanning, dates, duplicates, export, API, built web UI (memoir_engine/static)
web/                    React + TypeScript source of the interface (Vite)
tools/                  put ExifTool here on Windows
docs/                   user guide, testing notes, decisions, original product spec, design mockups
```

## For developers

```
cd engine && pip install -r requirements-dev.txt && python -m pytest tests     # 19 engine tests
cd web && npm ci && npm test && npm run build                                  # 15 UI tests; build writes engine/memoir_engine/static
cd web && npm run dev                                                          # UI on :5173, proxies /api to :8787
```

Status, test coverage and known limits: `docs/TESTING.md`. License: not chosen yet (MIT is a common choice).
