"""Create a synthetic sample photo folder for testing (no real/private photos).

    backend\\.venv\\Scripts\\python scripts\\make_sample_photos.py OUT_DIR [--music MUSIC_DIR]

Covers every date source, an exact duplicate, a recompressed look-alike, a
burst, a festival day (Deepavali 2022), "on this day" photos for today's date
in an earlier year, HEIC/PNG/WEBP/MP4, a broken file and a hidden folder.
OUT_DIR must not exist yet (the script never overwrites anything).
"""

import argparse
import io
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageDraw, ImageEnhance

pillow_heif.register_heif_opener()

FIXED_MTIME = datetime(2018, 6, 1, 12, 0, 0).timestamp()


def picture(seed: int, label: str, size=(800, 600)) -> Image.Image:
    """A distinct photo-like image: smooth colour blobs plus a caption."""
    rng = np.random.default_rng(seed)
    small = rng.integers(30, 230, (6, 8, 3), dtype=np.uint8)
    img = Image.fromarray(small).resize(size, Image.Resampling.BICUBIC)
    d = ImageDraw.Draw(img)
    d.rectangle((0, size[1] - 56, size[0], size[1]), fill=(0, 0, 0))
    d.text((16, size[1] - 44), label, fill=(255, 255, 255), font_size=28)
    return img


def exif_bytes(when: datetime | None) -> bytes:
    exif = Image.Exif()
    if when:
        exif.get_ifd(0x8769)[36867] = when.strftime("%Y:%m:%d %H:%M:%S")
        exif[271], exif[272] = "SampleCam", "SampleCam S1"
    return exif.tobytes()


def jpeg(path: Path, img: Image.Image, when: datetime | None = None, quality: int = 90) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=quality, exif=exif_bytes(when))


def video(path: Path, seconds: int = 2, size=(320, 240)) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 15, size)
    for i in range(15 * seconds):
        frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
        frame[:] = (40 + i * 3 % 200, 90, 160)
        cv2.circle(frame, (20 + i * 9 % (size[0] - 40), size[1] // 2), 18, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def build(out: Path, today: date) -> list[str]:
    made: list[Path] = []

    def add(p: Path) -> Path:
        p.parent.mkdir(parents=True, exist_ok=True)
        made.append(p)
        return p

    # 2019: a day trip (EXIF) -> one event
    for i in range(4):
        when = datetime(2019, 12, 20, 9 + i, 15)
        jpeg(add(out / "2019 Trip" / f"DSC_{100 + i:04d}.jpg"), picture(10 + i, f"Trip 2019 #{i + 1}"), when)

    # 2021: WhatsApp names only (filename dates) -> monthly moments
    jpeg(add(out / "WhatsApp" / "WhatsApp Image 2021-03-04 at 5.06.07 PM.jpeg"), picture(20, "WhatsApp long name"))
    jpeg(add(out / "WhatsApp" / "IMG-20210307-WA0003.jpg"), picture(21, "WhatsApp short name"))

    # Deepavali 2022 (24 Oct) -> festival event
    for i in range(3):
        when = datetime(2022, 10, 24, 19, 10 * i)
        jpeg(add(out / "Festivals" / f"IMG_20221024_19{10 * i:02d}00.jpg"), picture(30 + i, f"Deepavali #{i + 1}"), when)

    # 2023: a burst (same minute, near-identical) + an exact copy + a recompressed look-alike
    base = picture(40, "Birthday cake")
    for i in range(3):
        when = datetime(2023, 6, 10, 11, 15, 1 + 2 * i)
        frame = ImageEnhance.Brightness(base).enhance(1 + 0.03 * i)
        jpeg(add(out / "2023" / f"IMG_20230610_1115{1 + 2 * i:02d}.jpg"), frame, when)
    party = picture(41, "Party guests")
    jpeg(add(out / "2023" / "IMG_20230610_143000.jpg"), party, datetime(2023, 6, 10, 14, 30))
    copy = add(out / "Backup" / "IMG_20230610_143000.jpg")  # byte-identical copy
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_bytes((out / "2023" / "IMG_20230610_143000.jpg").read_bytes())
    buf = io.BytesIO()
    party.resize((400, 300)).save(buf, "JPEG", quality=55)
    jpeg(add(out / "Edited" / "party_small.jpg"), Image.open(buf), datetime(2023, 6, 10, 14, 30))

    # 2024: school function (IMG_ names + EXIF) and a video
    for i in range(3):
        when = datetime(2024, 6, 15, 9, 30 + 10 * i)
        jpeg(add(out / "2024" / f"IMG_20240615_09{30 + 10 * i:02d}00.jpg"), picture(50 + i, f"School day #{i + 1}"), when)
    video(add(out / "2024" / "VID_20240102_030405.mp4"))

    # On this day: today's date two years ago
    otd = today.replace(year=today.year - 2) if not (today.month == 2 and today.day == 29) else date(today.year - 2, 2, 28)
    for i in range(2):
        when = datetime.combine(otd, datetime.min.time()) + timedelta(hours=10, minutes=5 * i)
        jpeg(add(out / "Recent" / f"onthisday_{i + 1}.jpg"), picture(60 + i, f"On this day #{i + 1}"), when)

    # other formats without dates (file modified time is used)
    picture(70, "PNG").save(add(out / "Misc" / "scan.png"))
    picture(71, "WEBP").save(add(out / "Misc" / "sticker.webp"))
    picture(72, "HEIC").save(add(out / "Misc" / "iphone.heic"))

    # things the scanner must handle gracefully
    add(out / "Misc" / "broken.jpg").write_bytes(b"this is not a jpeg")
    add(out / "Misc" / "notes.txt").write_text("not media")
    jpeg(add(out / ".hidden" / "skip.jpg"), picture(80, "hidden"))

    for p in made:
        if "Misc" in p.parts and p.suffix != ".txt":
            os.utime(p, (FIXED_MTIME, FIXED_MTIME))
    return sorted(p.relative_to(out).as_posix() for p in made)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--music", type=Path, help="also create a folder with two tiny fake songs")
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()
    if args.out.exists():
        print(f"{args.out} already exists; choose a new folder", file=sys.stderr)
        return 1
    files = build(args.out, args.today)
    if args.music:
        if args.music.exists():
            print(f"{args.music} already exists", file=sys.stderr)
            return 1
        args.music.mkdir(parents=True)
        for name in ("Morning_Raga.mp3", "family_song.m4a"):
            (args.music / name).write_bytes(b"ID3" + bytes(64))
    print(f"created {len(files)} files in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
