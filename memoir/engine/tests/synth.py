"""Builds a synthetic Google Takeout (two ZIP parts, part 002 missing) for tests."""
import json
import os
import subprocess
import zipfile
from datetime import datetime, timezone

from PIL import Image

P = "Takeout/Google Photos/"


def _img(path, seed):
    im = Image.new("RGB", (64, 48), ((seed * 37) % 255, (seed * 91) % 255, (seed * 53) % 255))
    for x in range(seed % 60):
        im.putpixel((x, seed % 48), (255, 255, 255))
    im.save(path, "JPEG", quality=90)


def _exif(path, date):
    subprocess.run(["exiftool", "-overwrite_original", "-q", f"-DateTimeOriginal={date}", path], check=True)


def _sc(ts):
    return json.dumps({"title": "x", "photoTakenTime": {"timestamp": str(int(ts)), "formatted": "x"}})


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()


def build(root):
    os.makedirs(root, exist_ok=True)
    w = os.path.join(root, "work")
    os.makedirs(w, exist_ok=True)
    files = {}  # inner -> local path or bytes

    def photo(name, seed, exif=None):
        p = os.path.join(w, f"{len(files)}_{seed}.jpg")
        _img(p, seed)
        if exif:
            _exif(p, exif)
        return p

    y23, goa = P + "Photos from 2023/", P + "Goa trip/"
    # part 1 ---------------------------------------------------------------
    part1, part3 = {}, {}
    p1 = photo("a", 1, "2023:05:14 11:02:00")
    part1[y23 + "IMG_0001.jpg"] = p1                                  # tz-only vs sidecar
    part1[y23 + "IMG_0001.jpg.supplemental-metadata.json"] = _sc(utc(2023, 5, 14, 5, 32))
    part1[goa + "IMG_0001.jpg"] = p1                                  # exact duplicate in album
    part1[goa + "IMG_0001.jpg.supplemental-metadata.json"] = _sc(utc(2023, 5, 14, 5, 32))
    part1[y23 + "IMG_0002.jpg"] = photo("b", 2, "2023:06:01 10:00:00")  # sidecar in part 3, conflicting
    part3[y23 + "IMG_0002.jpg.json"] = _sc(utc(2021, 1, 1))
    part1[y23 + "IMG-20230514-WA0031.jpg"] = photo("c", 3)             # filename date only
    part1[y23 + "nodate.jpg"] = photo("d", 4)                          # missing
    part1[y23 + "IMG_0003.jpg"] = photo("e", 5)
    part1[y23 + "IMG_0003.jpg.json"] = _sc(utc(2022, 3, 3, 9))
    part1[y23 + "IMG_0003(1).jpg"] = photo("f", 6)                     # numbered
    part1[y23 + "IMG_0003.jpg(1).json"] = _sc(utc(2022, 3, 4, 9))
    part1[y23 + "IMG_0004.jpg"] = photo("g", 7)
    part1[y23 + "IMG_0004-edited.jpg"] = photo("h", 8)                 # edited uses original's json
    part1[y23 + "IMG_0004.jpg.json"] = _sc(utc(2022, 7, 7, 7))
    long = "a_very_long_photo_name_that_exceeds_the_limit_1234567890.jpg"
    part1[y23 + long] = photo("i", 9)
    part1[y23 + long[:44] + ".json"] = _sc(utc(2020, 2, 2, 2))        # truncated sidecar name
    part1[y23 + "corrupt.jpg"] = b"this is not an image at all" * 5
    part1[y23 + "sentinel.jpg"] = photo("j", 10, "1970:01:01 00:00:00")
    part1[y23 + "IMG_0100.jpg"] = photo("k", 11, "2023:08:08 08:08:08")  # live photo still
    vid = os.path.join(w, "live.mov")
    subprocess.run("ffmpeg -loglevel error -y -f lavfi -i testsrc=size=64x48:rate=5 -t 1 -pix_fmt yuv420p -f mp4 " + vid,
                   shell=True, check=True)
    part1[y23 + "IMG_0100.mov"] = vid                                  # live photo video
    clip = os.path.join(w, "clip.mp4")
    subprocess.run("ffmpeg -loglevel error -y -f lavfi -i testsrc=size=64x48:rate=5 -t 1 -pix_fmt yuv420p "
                   "-metadata creation_time=2022-08-01T10:00:00Z " + clip, shell=True, check=True)
    part1[y23 + "clip.mp4"] = clip
    part1[y23 + "random.txt"] = "ignored"                              # not media
    part1["Takeout/Google Photos/Goa trip/metadata.json"] = "{}"       # album metadata, ignored
    part1["__MACOSX/._junk.jpg"] = b"junk"

    def write_zip(path, items):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for inner, src in items.items():
                if isinstance(src, str) and os.path.exists(src):
                    z.write(src, inner)
                else:
                    z.writestr(inner, src if isinstance(src, (str, bytes)) else "")

    z1 = os.path.join(root, "takeout-20231001T000000Z-001.zip")
    z3 = os.path.join(root, "takeout-20231001T000000Z-003.zip")
    part3[y23 + "IMG_part3.jpg"] = photo("l", 12, "2019:12:25 18:30:00")
    write_zip(z1, part1)
    write_zip(z3, part3)
    # loose folder source
    loose = os.path.join(root, "loose")
    os.makedirs(loose, exist_ok=True)
    _img(os.path.join(loose, "PXL_20240102_030405.jpg"), 13)
    return {"z1": z1, "z3": z3, "loose": loose, "root": root}
