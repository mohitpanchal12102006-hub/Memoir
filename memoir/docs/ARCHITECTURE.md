# Architecture notes (from the design phase)

## Processing pipeline (Takeout 200+ GB, many ZIPs)

| Stage | What | Cost |
|---|---|---|
| 1 Index | Read each ZIP central directory (at the end of the file): path, size, position | Minutes |
| 2 Match sidecars | Pair JSON sidecars with media across all parts | Seconds |
| 3 Deep scan | One sequential pass per ZIP: read first KBs for dates, full streaming hash | Hours |
| 4 Resolve | Date waterfall, conflicts, duplicates | Fast |
| 5 Previews | Lazy, only for visible tiles; capped, clearable thumbnail cache | On demand |

Each stage is resumable (persistent catalog plus job journal). Process each ZIP sequentially, not randomly across parts.

## Takeout sidecar matching (carry into Phase 2)

- Truncated JSON names (Takeout shortens long names); newer exports use `.supplemental-metadata.json`.
- Numbered duplicates: `IMG_1234(1).jpg` pairs with `IMG_1234.jpg(1).json`.
- `-edited` photos reuse the original's JSON.
- Matching runs on the combined index; unmatched sidecars are shown as orphans (often a missing part).
- Group parts by export timestamp and numbering; flag gaps.

## Export (streaming, safe)

Read from ZIP, write to destination under a temporary name, write metadata, verify checksum, rename. Extra disk use is about one file. Resumable manifest. Sources never modified or auto-deleted. Optional second target for a subset.

## Preview strategy (browser)

1. Native: JPG, PNG, WEBP, GIF, AVIF, BMP; MP4/MOV (H.264), WebM.
2. HEIC/HEIF: libheif-js (WASM) in a worker; Safari natively.
3. RAW: extract the embedded JPEG preview (exifr thumbnail plus a small parser); LibRaw WASM fallback.
4. Unsupported video: detect with MediaCapabilities, ffmpeg.wasm poster frame in memory.
5. Placeholder tile as last resort.

Never read whole files into memory; use `File.slice()`; limit decoders to 2 to 4 workers.

## User flow

```
Upload -> Scan stages -> Summary -> Timeline <------------+
                                      |                    |
                                      v                    |
                                 Needs Review -> fix single / batch (undo)
                                      |
Timeline -> Duplicates (optional) -> Export dialog -> Preflight -> Progress -> Report
```

Edge states: unsupported or corrupt file (placeholder, goes to review), preview failure, sentinel dates (1970, 1980, future), timezone-only differences, drive offline, re-scan keeps manual decisions.

## Component hierarchy

```
<App>
 AppProviders (theme, store, PreviewProvider, toasts)
  AppShell: TopBar (SessionSummary, ExportButton, DriveStatusBar), Nav, Routes
   /upload     Dropzone, TerminalBox, FormatTicker, TakeoutSetPanel(PartsBar), ScanProgress, JobCenter
   /timeline   Toolbar, Scrubber, VirtualGrid(DateGroupHeader, MediaTile), ViewerDrawer(UniversalPreviewer, MetadataTable)
   /review     Queue(ReasonFilterChips, QueueItem), Workspace(UniversalPreviewer, ClueStrip, MetadataCompare, DateTimeEditor, BatchEditBar, Actions), OrphanSidecars
   /duplicates SummaryBar, ModeSelector, FolderRemovalPlan, GroupCard, KeeperRules, RemovalPlanDialog
 ExportDialog: Destination, Organization, Preflight(DiskSpaceMeter), Progress
 ResumeBanner, RelinkDialog
```

## Wireframes (structure)

```
UPLOAD
+------------------------------------------------------------+
| Memoir        Upload  Timeline  Review 73  Duplicates 184  [Export] |
+------------------------------------------------------------+
| 01 UPLOAD                                  [tall nature image]
| Keep every moment, in its place.
| $ memoir index /Volumes/SSD/takeout-*.zip_
| JPG HEIC RAW DNG CR3 MP4 MOV MKV ...  (ticker)
| Takeout set: 15 parts, 214 GB   [##########x#.#...]  part 009 missing
| Images 8,120 | RAW 340 | Video 951 | Other 12     [Pause] [Open timeline]
+------------------------------------------------------------+

TIMELINE
| [nature banner: Timeline]
| search  [Type][Format][Source]
| 14 March 2024   6 items                                  2024
| [ ][ ][ ][ ][ ][REVIEW]                                  2023
| 13 March 2024   6 items                                  2022
| [ ][ ][ ][ ][ ][REVIEW]

NEEDS REVIEW
| queue (chips + checkable list) | preview | clues + neighbors
|                                | candidates table (EXIF / Sidecar / Filename, Use)
|                                | date | time | tz offset   [Apply][Skip][Undo]
| [Batch edit (n selected)]

DUPLICATES
| 184 groups, 412 extra files, 3.9 GB reclaimable   [Exact 171][Similar 13]
| Mode: [Exclude from export] [Quarantine] [Delete]
| Removal plan by folder        | Group 12 of 184: IMG_4021.HEIC
|  [x] Albums/Goa trip  112     |  KEEP   Photos from 2023/IMG_4021.HEIC
|  [x] Albums/Favourites 96     |  REMOVE Removing from: Albums/Goa trip  [Keep this one]
|  [x] WhatsApp/Sent     61     |  [Prev] [Skip] [Next]
| [Review removal plan]

REMOVAL PLAN DIALOG
| Folder                Removing  Keeping
| Albums/Goa trip          112       0
| Albums/Favourites         96       0
| WhatsApp Images/Sent      61       0
| Photos from 2023           0     171
| Total 412 files, 3.9 GB     [x] Save removal report (CSV)   [Cancel][Apply plan]
```

## Neumorphism tokens (explored, not chosen; kept for reference)

```css
:root{--bg:#e0e5ec;--shadow-light:#fff;--shadow-dark:#a3b1c6;--text:#2d3748;--text-muted:#5b6778;--accent:#2a49b8;
--raised:8px 8px 16px var(--shadow-dark),-8px -8px 16px var(--shadow-light);
--inset:inset 6px 6px 12px var(--shadow-dark),inset -6px -6px 12px var(--shadow-light)}
```
