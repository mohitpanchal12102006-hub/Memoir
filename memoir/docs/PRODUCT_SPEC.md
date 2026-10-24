# Project Specification: Memoir — Universal Lossless Media Chronology & Google Takeout Organizer WebApp

## 1. Project Overview
**Memoir** is a web application that organizes photos and videos extracted from `.zip` files, local folders, or **Google Takeout** archives. **Memoir** restores and organizes media files chronologically based on their exact capture date and time, allows manual conflict resolution for missing or ambiguous dates, and exports the organized media with **zero quality loss**.

The app must universally read, preview, and arrange **all types of photo and video formats** regardless of which phone, camera, operating system, or social media platform they originated from. Furthermore, the chronological order must persist permanently across any device (laptop file explorer, macOS Finder, Android/iOS phone galleries) and survive file transfers across different storage mediums.

---

## 2. Core Functional Requirements

### A. Universal Format & Cross-Platform Compatibility
**Memoir** must support media from any device or platform without failing or skipping files:
* **Standard & Modern Image Formats:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`, `.bmp`, `.tiff`, `.avif`, and Apple's `.heic` / `.heif` (including iOS Live Photos where `.heic` and `.mov` are paired).
* **RAW Camera Formats (DSLR & Smartphone Pro Modes):** `.dng` (Android/Apple ProRAW), `.cr2` / `.cr3` (Canon), `.nef` (Nikon), `.arw` (Sony), `.orf`, `.rw2`.
* **Universal Video Containers & Codecs:** `.mp4`, `.mov` (iPhone/QuickTime), `.mkv`, `.avi`, `.webm`, `.3gp` (older phones), `.m4v`, `.mts` / `.m2ts` (camcorders), covering both H.264, H.265/HEVC, VP9, and AV1 codecs.
* **Platform-Stripped Media (Social & Messaging Apps):** Media downloaded from WhatsApp, Telegram, Instagram, Snapchat, or Facebook where internal EXIF metadata was stripped by the platform.

### B. Ingestion & Smart Date Extraction Priority
* **Supported Inputs:** Standard folders, `.zip` archives, and **Google Takeout** archives (including `.json` sidecar metadata files, handling truncated or weirdly named Google Takeout JSON files accurately).
* **Date Extraction Priority Waterfall:**
  1. **Embedded Metadata:** `EXIF:DateTimeOriginal`, `EXIF:CreateDate`, `XMP:CreateDate`, `QuickTime:CreationDate`, `Keys:CreationDate` (iOS), and `ID3`/container tags.
  2. **Google Takeout Sidecars:** `.json` files (`photoTakenTime.timestamp`).
  3. **Platform-Specific Filename Regex:** Parse dates from naming conventions across all platforms:
     * Android/Pixel/Samsung (`IMG_YYYYMMDD_HHMMSS`, `PXL_YYYYMMDD_HHMMSS`)
     * WhatsApp (`IMG-YYYYMMDD-WAXXXX`, `VID-YYYYMMDD-WAXXXX`)
     * Screenshots (`Screenshot_YYYY-MM-DD-HH-MM-SS`, `Screen Shot YYYY-MM-DD at HH.MM.SS`)
     * Snapchat/Instagram/Telegram epoch or date-stamped filenames.

### C. Conflict & Error Resolution UI (Manual Fixing)
* If a photo or video has missing capture date metadata, corrupted headers, or conflicting dates (e.g., EXIF date vs. JSON date mismatch, or WhatsApp forward date vs. actual creation date), flag the file in a **"Needs Review / Conflict"** queue.
* **Browser Preview Compatibility:** Because browsers cannot natively render `.heic`, `.mkv`, or `.dng` RAW files out-of-the-box, the UI must generate lightweight, temporary in-memory preview thumbnails for the user interface **without modifying the underlying original file**.
* Provide a visual workspace where the user can inspect the flagged photo/video, view available clues (filename, folder name, adjacent photos in the batch), and manually assign or batch-edit the correct date and time.

### D. Lossless Quality Preservation
* **Strict Zero Re-compression Policy:** Do NOT re-encode, transcode, or compress images or videos during export. Original bitrates, resolutions, frame rates, HDR data, color profiles, and pixel data must remain 100% bit-for-bit identical. Only metadata headers and file system attributes may be modified.

### E. Cross-Device & Cross-Transfer Persistence (Crucial)
When the user exports the final batch from **Memoir** and opens it on a laptop gallery, phone gallery (iOS Photos, Google Photos, Samsung Gallery), or transfers it between devices, the exact chronological arrangement must stay intact. To guarantee this, the export process must apply three layers of persistence:
1. **Internal Metadata Embedding:** Write the finalized capture date directly into the file's internal headers (`EXIF:DateTimeOriginal`, `EXIF:CreateDate`, `XMP:CreateDate` for images/RAWs; `QuickTime:CreateDate`, `TrackCreateDate`, `MediaCreateDate`, and `Keys:CreationDate` for videos). *Phone and laptop galleries rely on these specific tags.*
2. **OS File System Timestamps:** Update the file's `mtime` (Last Modified Time) and `ctime`/`birthtime` (Creation Time) to match the capture date before packaging.
3. **Chronological Filename Prefixing / Folder Structure:** Optionally rename or organize files using an ISO-8601 prefix (e.g., `YYYY-MM-DD_HH-MM-SS_OriginalName.ext` or `YYYY/MM/` folders) so even basic file explorers sort them identically after file transfers.

---

## 3. Development Workflow (Step-by-Step Execution Plan)
**Memoir** is designed and built in two distinct phases. Do not jump to the backend until the frontend design is finalized.

### Phase 1: Frontend Architecture & UI/UX Design
* **Upload & Dropzone View:** Drag-and-drop interface supporting large ZIPs, Google Takeout archives, and folders containing any photo/video format.
* **Dashboard & Timeline View:** Visual grid showing successfully parsed media arranged chronologically, including support for rendering non-web formats (like HEIC/MOV/MKV) in the preview UI.
* **Conflict Resolution Workspace:** Dedicated UI tab for flagged/conflicting files with a universal media previewer, side-by-side metadata comparison, and a quick date/time picker (for single and batch fixing).
* **Export Configuration Modal:** Options to download as a single organized `.zip` or write directly to a local directory (using the File System Access API), preserving all timestamps and original quality.

### Phase 2: Backend & Processing Engine (requires approval before starting)
* File extraction and stream handling (handling large multi-gigabyte archives without crashing memory).
* Universal metadata parser & JSON sidecar matcher for Google Takeout (`exiftool` integration to support 100% of photo/RAW/video containers losslessly).
* Lossless timestamp injection and ZIP stream generation with explicit timestamp retention.

---

## 4. Additions agreed during Phase 1 design
* **Duplicate removal:** detect exact and similar duplicates; always show which folder each file is removed from; non-destructive by default (exclude from export), optional quarantine, delete only with explicit confirmation.
* **Scale:** Google Takeout of 200+ GB across many ZIP parts; read in place, resumable, ZIP parts on laptop or external SSD.
* **Interface:** Luxury + motion visual direction (see PHASE1_SPEC.md).
