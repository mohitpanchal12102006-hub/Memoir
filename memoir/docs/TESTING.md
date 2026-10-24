# Testing notes (what was verified, and what was not)

## Verified automatically
- **Engine (19 tests, `engine/tests`)**: a synthetic Takeout with two ZIP parts (part 002 missing) and a loose folder covering:
  cross-part sidecars, truncated sidecar names, numbered copies, `-edited` photos, `.supplemental-metadata.json`, timezone-only differences,
  conflicting dates, WhatsApp/Android/Pixel filenames, placeholder dates (1970), corrupt files, bad ZIP checksums, unicode names,
  Live Photo pairing, exact and similar duplicates, quarantine, previews (photo, video, placeholder), folder and ZIP export,
  sidecar timezone option, resume after interruption, drive-offline pause and resume, cancel and resume, one job at a time,
  local-only request guard.
- **Lossless check**: exported JPEG pixel data and metadata-stripped bytes are identical to the original; exported MP4 frames are identical (frame MD5).
- **Interface (15 tests, `web/src/test`)**: formatting, timeline row model, API error handling, every page rendered against a mocked API.
- **Real browser end to end** (headless Chromium against the real server): folder picker, adding ZIP parts, scan, timeline with real previews,
  fixing a date, removing a duplicate, export preflight and export. No console errors, page errors or failed requests.
- **Clean install**: the engine installs into a fresh virtualenv with `pip install` and serves the built interface.
- **Scale**: 250,000 catalog items across 20 ZIP parts: paging 8 ms (first page) to 0.4 s (deep page), timeline 0.2 s, review counts 0.05 s,
  duplicate pages under 0.1 s once indexed. Scan speed measured at about 320 small photos per second.

## Not verified (please be aware)
- **A real 200 GB Takeout.** Design and tests target that size, but it was not run end to end here. Large files are limited by your drive speed.
- **Windows and macOS.** Tested on Linux only. Windows creation-time setting (`SetFileTime`) and macOS behaviour are implemented but untested on those systems.
- **Real HEIC, RAW (CR3, NEF, ARW, DNG) and MKV files.** ExifTool supports many of these for writing, but only JPEG and MP4 were tested. Formats ExifTool cannot write
  (such as MKV, AVI) are copied with file times and date-prefixed names, and the report says the date was not embedded.
- **Delete from source** is intentionally not implemented. Similar-video detection is not implemented (similar detection covers images only).
- Drag and drop of files is not possible in a browser app (browsers hide file paths); use the built-in picker or paste paths.
- A missing **last** ZIP part cannot be detected (only gaps below the highest part present).
