ExifTool is required (it reads and writes capture dates without touching picture data).

Easiest way on Windows:
  1. Download the Windows ZIP from https://exiftool.org
  2. Unzip it. You get "exiftool(-k).exe" and a folder "exiftool_files".
  3. Rename "exiftool(-k).exe" to "exiftool.exe".
  4. Put BOTH "exiftool.exe" and the "exiftool_files" folder in this "tools" folder.

macOS:  brew install exiftool      (or use the installer from exiftool.org)
Linux:  sudo apt install libimage-exiftool-perl

Memoir finds ExifTool in this folder first, then on your PATH.
Optional: ffmpeg (https://ffmpeg.org) gives preview pictures for videos such as MKV and AVI.
