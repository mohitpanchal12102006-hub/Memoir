# Memoir user guide

## 1. Get your Google Takeout
Download every ZIP part of your Takeout (named like `takeout-20231001T000000Z-001.zip`, `-002`, ...). Keep them together.
They can be on your laptop or on an external drive. Do not unzip them.

## 2. Add them
Open **Upload**. Press **Choose ZIP parts or folders**, browse to the folder that holds the ZIP parts, tick the parts
(or press **Use this folder** to add all ZIPs in it). You can also paste paths. The page shows each part; a hatched red
block means a part is missing (for example part 002), and Memoir tells you which.

## 3. Scan
Press **Start scan**. Memoir reads every ZIP directory, matches Google's JSON files, then reads each file once to get
its dates and a fingerprint. You can **Pause**, **Resume** or **Cancel** at any time, and close the window: the scan
continues where it stopped the next time you press **Resume scan**. If a drive is unplugged the scan pauses; plug it
in and press **Resume**. Large archives take a long time (hours for hundreds of GB). The speed is shown as MB/s with an estimate.

## 4. Browse the Timeline
Photos appear in order by capture date. Filter by type, format or source, search names, click a year to jump.
Click a photo for its details and where its date came from.

## 5. Fix doubtful dates (Needs review)
Each file shows its clues: the dates found, the file name, the folder, and nearby photos. Press **Use** next to the right date,
or type a date and time and press **Apply**. For many files at once use **Change many at once**: set a date, shift by minutes,
or space files a few seconds apart. **Undo** reverses the last change. Keys: J/K move, U undoes.

If a date is only in Google's JSON (UTC), set your timezone (for example +05:30) in the Export dialog so local times are right.

## 6. Remove duplicates (optional)
Open **Duplicates**. Each group shows the copy to **Keep** and the copies to **Remove**, with **Removing from: <folder>**.
Untick folders you want to leave alone, press **Review removal plan**, and confirm. By default the extra copies are only
left out of the export. **Undo all removals** restores everything. Similar (not identical) images are found on demand and are never
removed unless you choose them.

## 7. Export
Press **Export**: choose a destination folder (or a ZIP file) on a drive with enough free space, choose the folder layout,
check the summary (space, filesystem, what is left out), and start. Each file is copied exactly, its capture date is written into it,
its file dates are set, and the name can start with the date. A report (CSV) is saved. If it stops, open Export and press **Resume it**.

Tips: export to a different drive than the one holding the ZIPs; use exFAT or NTFS (FAT32 cannot hold files over 4 GB
and stores times coarsely).

## Troubleshooting
- "exiftool was not found": see `tools/README.txt`, then restart Memoir.
- A video shows a placeholder: install ffmpeg for previews. The video is still exported correctly.
- "Not enough free space": choose another destination or use the date range to export part of the archive.
- Photos with no date: they stay in Needs review. Fix them, or export them into an `_Unsorted` folder.
