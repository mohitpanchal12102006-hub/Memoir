# Memoir: Phase 1 Build Spec (Frontend)

> Status: implemented. This spec is kept as the design record. See README.md for how to run the finished app and docs/DECISIONS.md for the build outcomes.

Status: Phase 1 only. No backend work until Phase 2 is explicitly approved.
Visual reference: the "Luxury + motion" page of the Memoir design canvas (https://claude.ai/artifact/2XFN4DXNBq7FbztjM8WB6d).

## 1. Scope

Build the Memoir web UI against a **mocked engine**. Screens: Upload, Timeline, Needs Review, Duplicates, plus the Export dialog. Everything the real engine will do (reading ZIPs, hashing, metadata writes) is faked behind an API contract (section 9) so Phase 2 can replace the mock without touching components.

Out of scope in Phase 1: ZIP extraction, hashing, exiftool, writing metadata or timestamps, deleting or moving files.

## 2. Product constraints the UI must respect

- **Lossless:** no re-encoding of any original. Previews are temporary, in-memory derivatives only.
- **Formats:** JPG, JPEG, PNG, WEBP, GIF, BMP, TIFF, AVIF, HEIC/HEIF (Live Photo pairs), RAW (DNG, CR2, CR3, NEF, ARW, ORF, RW2), MP4, MOV, MKV, AVI, WEBM, 3GP, M4V, MTS/M2TS (H.264, HEVC, VP9, AV1). Platform-stripped media from WhatsApp, Telegram, Instagram, Snapchat, Facebook.
- **Date waterfall (display order of clues):** embedded metadata, then Takeout JSON sidecar, then filename pattern. Conflicts and missing dates go to Needs Review.
- **Export persistence layers:** (1) embedded date tags, (2) file system timestamps, (3) optional ISO filename prefix / `YYYY/MM/` folders. Layers 1 and 2 are always on in the UI; layer 3 is optional.
- **Safety:** sources are read-only. Removal of duplicates is non-destructive by default.

## 3. Scale and drive requirements

Design for a Google Takeout of **200+ GB across 15 to 20+ ZIP parts**, ZIP parts on the **laptop or an external SSD**, and 250k+ media items.

- Never extract ZIPs to disk first. Parts are read in place; export streams one file at a time.
- Pipeline stages, each resumable: 1 Index ZIP directories, 2 Match sidecars (across all parts), 3 Deep scan (dates and hashes), 4 Resolve (conflicts and duplicates), 5 Lazy previews.
- The UI never holds all items: windowed queries by date range, virtualized grid, selection stored as IDs or as a query rule ("all files in this folder").
- Parts show a location badge (Laptop or External SSD). A set can span both.
- Drive offline: the job pauses, the part is marked offline, resume when it returns. Re-link dialog if the drive letter changes.
- Export preflight shows: free space vs selected size, destination filesystem (warn on FAT32: 4 GB file limit and 2-second timestamps), and a warning when source and destination share a drive.
- Missing parts are detected from numbering (for example part 009 missing) and shown in the set panel and as orphan sidecars in Needs Review.

## 4. Visual direction: Luxury + motion

Dark, quiet, editorial. Calm nature imagery. Serif display type. Hairlines instead of shadows.

### Tokens

```css
:root {
  --bg: #111110;        --surface: #171715;
  --text: #ece8df;      --muted: #9b968c;
  --hair: #2a2926;      --line: #4a4740;
  --accent: #c8b07a;    --accent-hi: #f3e4cf;
  --keep: #9fc3a4;      --remove: #e8907f;
  --font-display: 'Cormorant Garamond', serif;
  --font-ui: 'Jost', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', monospace;
  --ease-out: cubic-bezier(.2,.7,.2,1);
  --ease-wipe: cubic-bezier(.7,0,.2,1);
}
```

Load fonts with `family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,400`, `Jost:wght@400;500`, `IBM+Plex+Mono:wght@400`. Always define real fallback stacks.

### Typography

| Use | Font | Spec |
|---|---|---|
| Page title (h1) | Display, 300 | 68px, hero 84px, line-height 1, tracking -0.01em |
| Section / date headers | Display, 400 | 30 to 36px |
| List titles, file names | Display, 400 | 20 to 24px |
| Body | UI, 400 | 14 to 15px |
| Labels, buttons, chips | UI, 500, uppercase | 11 to 12px, tracking 0.16 to 0.24em |
| Terminal, ticker, hashes | Mono | 12 to 14px |

### Components

- Buttons: hairline `--line` border, uppercase tracked label. Primary is solid `--accent` with `--bg` text.
- Chips: hairline border; active chip uses `--accent` border and `--text` color.
- Inputs: underline only (`--line`), no box.
- Tables and lists: hairline row dividers, no zebra.
- Tiles: 3:4, sharp corners, no radius. Format label bottom-left, REVIEW flag top-right in `--accent`.
- Status colors always come with a text label: KEEP (`--keep`), REMOVE (`--remove`).
- Contrast: all text at least WCAG AA against `--bg`. Check `--muted` on every surface it appears on.

### Motion catalog

| Effect | Where | Spec |
|---|---|---|
| Staggered fade-up | Every page, each section | 1s `--ease-out`, 0.1s steps |
| Headline wipe | Every h1 | `clip-path: inset(-10% 100% -10% 0)` to `inset(-10% -2% -10% 0)`, 1.3s `--ease-wipe`, 0.3s delay |
| Typed terminal | Upload | `width: 0` to `41ch`, `steps(41)`, 3.2s, with a blinking cursor |
| Travelling border light | Terminal box | `@property --a` angle, `conic-gradient(from var(--a), ...)` border, 6s linear loop |
| Format ticker | Upload | Duplicated track, `translateX(-50%)`, 30s linear loop |
| Parts bar | Upload | 15 segments: done (accent), indexing (pulse 1.2s), missing (hatched `--remove`), queued (outline) |
| Hero drift | Hero and banner images | slow scale 1.04 to 1.10 and 2% pan, 22s ease-in-out loop |
| Mist, sun glow, birds | Hero and banner | mist drifts 15s alternate; sun glow pulses 6s; birds cross 17s linear |
| Outlined numerals 01 to 04 | Behind each page | `-webkit-text-stroke` only, floats 22px over 9s alternate |
| Tile hover | Grid | lift 6px, image zoom 1.14 over 1.4s, light sweep across |
| Button hover | All buttons | gold wipe from the left in 0.55s; primary inverts to outline |
| Nav underline | Top nav | slides in from left on hover and for the active item |

All motion must respect `prefers-reduced-motion: reduce` (disable animations and transitions, show the typed command fully).

### Imagery

- Calm nature photography for the Upload hero (tall), the Timeline banner (wide panorama) and placeholder tiles.
- Use the user's own photos or free-license sources only. Store in `web/public/img/`, compress as WebP or AVIF, and always provide `alt` text.
- Until real photos are added, use the inline SVG landscape scenes from the design canvas as placeholders.

## 5. Tech stack

React 18, TypeScript, Vite (SPA), Tailwind with CSS variables for the tokens, Radix UI primitives, Zustand (normalized `mediaById`), TanStack Virtual, TanStack Query, Zod, date-fns and date-fns-tz, Comlink and Web Workers, zip.js (preview-level ZIP reads), exifr (preview-level metadata), libheif-js (HEIC preview), ffmpeg.wasm (poster frames for unsupported video), MSW (mock API), Vitest, Playwright, Storybook, pnpm.

## 6. Repository structure

```
memoir/
  README.md  LICENSE  CONTRIBUTING.md
  .github/workflows/ci.yml
  docs/  wireframes/  adr/  api-contract.md
  web/
    public/  wasm/  img/
    src/
      app/            App.tsx, router, providers
      features/
        upload/       Dropzone, TakeoutSetPanel, PartsBar, TerminalBox, FormatTicker
        timeline/     VirtualGrid, DateGroupHeader, Scrubber, Toolbar, ViewerDrawer
        review/       Queue, Workspace, MetadataCompare, DateTimeEditor, BatchBar, OrphanSidecars
        duplicates/   Page, SummaryBar, FolderRemovalPlan, GroupCard, KeeperRules, RemovalPlanDialog
        export/       ExportDialog, Destination, Organization, Preflight, Progress
        jobs/         JobCenter, ResumeBanner, DriveStatusBar, RelinkDialog
      components/ui/  buttons, chips, inputs, table, dialog
      components/media/  MediaTile, UniversalPreviewer, MetadataTable, SourceLocationBadge
      preview/        PreviewProvider.ts, tiers, workers/, cache.ts
      catalog/        windowed queries (mocked)
      domain/         types.ts, dateWaterfall.ts, filenamePatterns.ts, duplicates.ts
      store/          ingest, media, resolution, ui, export
      api/            client.ts, contract.ts, mocks/ (MSW)
      styles/         tokens.css, motion.css
    e2e/
  engine/             Phase 2 placeholder README only
```

If this goes into the existing Memoir repo, `web/` replaces the current vanilla-JS UI and the existing Python/FastAPI code moves under `engine/`.

## 7. Domain model

```ts
type DateCandidate = {
  source: 'exif' | 'xmp' | 'quicktime' | 'sidecar' | 'filename' | 'folder' | 'manual';
  tag?: string; value: string; tzOffset?: string; confidence: number;
};

type ConflictReason =
  | 'missing' | 'corrupt' | 'exif_vs_sidecar' | 'filename_vs_exif'
  | 'forward_date' | 'placeholder_date' | 'tz_only';

type MediaItem = {
  id: string; name: string; path: string; size: number;
  kind: 'image' | 'raw' | 'video'; format: string;
  partId?: string; livePairId?: string;
  candidates: DateCandidate[];
  resolved?: { value: string; source: DateCandidate['source'] };
  status: 'ok' | 'review' | 'fixed';
  conflictReasons: ConflictReason[];
  preview: 'idle' | 'loading' | 'ready' | 'failed';
};

type TakeoutPart = {
  id: string; name: string; partNumber: number; sizeBytes: number;
  location: { drive: string; volumeId: string; kind: 'internal' | 'external' };
  state: 'queued' | 'indexing' | 'indexed' | 'scanning' | 'done' | 'offline' | 'missing' | 'error';
};

type DuplicateGroup = {
  id: string; kind: 'exact' | 'similar';
  members: { mediaId: string; folder: string; role: 'keep' | 'remove' }[];
  reclaimableBytes: number;
};

type Job = {
  id: string; type: 'index' | 'scan' | 'resolve' | 'export';
  state: 'running' | 'paused' | 'done' | 'error';
  progress: { done: number; total: number; mbPerSec?: number; etaSec?: number };
};
```

A timezone-only difference between EXIF (local, no offset) and sidecar (UTC) is `tz_only`: show it as "likely timezone difference" and treat it as low priority.

## 8. Screens

### Upload
Hero headline with italic subtitle and a tall nature image (drift, mist, sun, birds). Terminal box with a typed sample command and travelling border light. Format ticker. "Drop ZIP parts or folders" with Choose folder and Choose all ZIP parts. Takeout set panel: part count, total size, missing-part warning, 15-segment parts bar, speed, ETA, "extracted to disk: 0 GB", resume point saved. Counts for Images, RAW, Video, Other. Pause and Open Timeline.
States: empty, indexing, partial (missing part), offline drive, resume banner, error.

### Timeline
Wide nature banner with the title. Toolbar: search, Type, Format, Source filters. Date groups with large serif dates and item counts. Virtualized 3:4 tile grid. Year scrubber on the right. Tile click opens a viewer drawer with the universal previewer, metadata, and date source. Review-flagged tiles carry a REVIEW label.

### Needs Review
Left: filter chips (All, Missing, Mismatch, Corrupt, Orphan sidecars) and a checkable queue. Right: large preview (in-memory), clues (filename date, folder, neighbors strip), candidate table with Use buttons, date, time and timezone offset fields, Apply, Skip, Undo. Batch edit: set date, shift by offset, space items every N seconds, apply to selection or to a query ("all files in this folder"). Undo history is required.

### Duplicates
Summary line (groups, extra files, reclaimable size), Exact and Similar tabs, removal mode selector (Exclude from export is the default; Move to quarantine; Delete from source needs typed confirmation). **Removal plan by folder** (checkbox, folder path, file count and size) and a group card that always shows `Removing from: <folder>` for the REMOVE member. Keeper rules in priority order: higher resolution, larger size, real embedded date, preferred folder type. Offer to copy a date from the removed copy to the keeper. Rules: a group always keeps at least one copy; only exact matches can be bulk-selected; similar matches are never auto-selected; a dry-run summary and a removal report (CSV or JSON: removed path, kept path, folder, hash) come before anything applies.

### Export dialog
Steps: Destination (ZIP or local folder, optional second target), Organization (structure, filename prefix, persistence layers 1 and 2 locked on), Preflight (space, filesystem, same-drive warning, duplicates excluded, files needing review), Progress (per-file verify, resumable). The dialog states honestly that a browser folder handle cannot guarantee file timestamps and that the local engine does the lossless writes.

## 9. Mock API contract (for Phase 2)

All lists are cursor-paginated. Long work runs as jobs reported over a server-sent event stream.

```
GET    /api/drives
POST   /api/sources                     { paths: string[] }
GET    /api/takeout-sets
POST   /api/jobs                        { type, params }
GET    /api/jobs/:id
GET    /api/events                      (SSE: job progress, part state changes)
GET    /api/media                       ?from&to&kind&status&folder&cursor&limit
GET    /api/media/:id
GET    /api/media/:id/preview           (Phase 2 backend thumbnails)
GET    /api/review                      ?reason&cursor
PATCH  /api/media/resolve               { ids | query, date, tzOffset }
GET    /api/duplicates                  ?kind&cursor
POST   /api/duplicates/plan             { mode, selections }
POST   /api/export/preflight            { destination, options }
POST   /api/export                      { destination, options, planId }
```

Validate every response with Zod. MSW serves fixtures, including a synthetic catalog of 300,000 items and 20 ZIP parts.

## 10. Preview pipeline

`PreviewProvider` is an interface so Phase 2 can add a backend implementation.

1. Native formats: object URL, `createImageBitmap`, `<video>`.
2. HEIC/HEIF: libheif-js in a worker (Safari decodes natively).
3. RAW: extract the embedded JPEG preview; fall back to a LibRaw WASM decode.
4. Unsupported video: detect with `MediaCapabilities`; ffmpeg.wasm extracts a poster frame in memory.
5. Last resort: file-type placeholder tile. No file ever disappears silently.

Pair Live Photos (`.heic` plus `.mov`) into one tile. Limit decoders to 2 to 4 workers. Keep an LRU in-memory cache plus an optional capped thumbnail cache (default 1 GB, clearable). Never call `file.arrayBuffer()` on a whole file; read slices.

## 11. Accessibility and quality

- Keyboard-first Review workspace (next, previous, apply, undo, select).
- Visible focus ring in `--accent` on every control.
- Labels on all inputs; status never conveyed by color alone.
- Responsive: Review stacks vertically on narrow screens; the Timeline drops to 2 or 3 columns.
- Unit tests for date waterfall, filename patterns, tz-only detection and keeper rules.
- Playwright flows for: upload with a missing part, resolve a conflict (single and batch), duplicate plan with folder breakdown, export preflight.

## 12. Definition of done for Phase 1

- All five screens match the visual reference and the motion catalog, with reduced-motion support.
- The Timeline scrolls smoothly over the 300k-item mock catalog; memory stays stable while scrolling.
- Every state in section 8 exists (empty, in progress, partial, offline, error).
- Contract types are generated from one source and validated with Zod.
- CI runs lint, type-check, unit and e2e tests.
- Nothing in the app touches real files.

## 13. Build order

1. Scaffold, tokens, fonts, motion.css, app shell and nav.
2. Domain types, API contract, MSW fixtures (300k items, 20 parts).
3. Upload screen and jobs components.
4. Timeline with virtualization and the viewer drawer.
5. Preview pipeline interface with the mock provider, then HEIC, RAW and video tiers.
6. Needs Review with single and batch editing and undo.
7. Duplicates with folder breakdown and removal plan.
8. Export dialog and preflight.
9. Tests, accessibility pass, polish, README.

## 14. Prompt for the coding agent

> Read `docs/PHASE1_SPEC.md` completely. Scaffold the `web/` app (React, TypeScript, Vite, Tailwind, Zustand, TanStack Virtual) exactly as in sections 5 and 6, with the tokens and motion from section 4. Implement build order steps 1 to 3 only: scaffold and design tokens, domain types with the API contract and MSW fixtures, and the Upload screen with the jobs components. Do not write any backend code and do not touch real files. When finished, give a short summary of what was done and what is next.
