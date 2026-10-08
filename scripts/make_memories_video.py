"""Render a "memories" movie from the library.

    python scripts/make_memories_video.py [--music song.mp3] [--folder-id 1]

Title card, a card per year, Ken Burns slides (portraits paired side by side),
short video clips, crossfades and date captions. Originals are opened
read-only; the MP4 is written only to <data>/exports/.
"""

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import pillow_heif  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import db, safety  # noqa: E402
from app.config import default_data_dir  # noqa: E402
from app.models import Media, SourceFolder  # noqa: E402
from app.scanner.thumbs import thumb_path  # noqa: E402

pillow_heif.register_heif_opener()

W, H = 1920, 1080
FPS = 30
OVER = 1.12  # slide canvas is this much larger than the frame, for zoom/pan room
CW, CH = round(W * OVER), round(H * OVER)
FADE_S = 0.9
PHOTO_S = 4.2
PAIR_S = 4.8
TITLE_S = 4.5
YEAR_S = 2.8
END_S = 4.0
VIDEO_MAX_S = 6.0

CREAM = (250, 244, 235)
GOLD = (226, 196, 146)
MUTED = (205, 196, 186)

FONT_DIR = Path(r"C:\Windows\Fonts")


def font(size: int, *names: str) -> ImageFont.FreeTypeFont:
    for n in names:
        if (FONT_DIR / n).is_file():
            return ImageFont.truetype(str(FONT_DIR / n), size)
    return ImageFont.load_default(size)


def serif(size):
    return font(size, "georgia.ttf", "pala.ttf", "times.ttf")


def serif_italic(size):
    return font(size, "georgiai.ttf", "palai.ttf", "timesi.ttf")


def sans(size):
    return font(size, "segoeui.ttf", "arial.ttf")


# ---------- image helpers ----------

# Per-file clockwise rotation fixes (--rotate NAME=DEG), for files recorded sideways
ROTATE: dict[str, int] = {}
CV_ROTATE = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def load_photo(path: Path, max_edge: int = 1800) -> Image.Image:
    with safety.open_source(path) as f, Image.open(f) as im:
        im.draft("RGB", (max_edge, max_edge))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    if deg := ROTATE.get(path.name.lower()):
        im = im.rotate(-deg, expand=True)
    return im


def rotate_frame(frame: np.ndarray, path: Path) -> np.ndarray:
    deg = ROTATE.get(path.name.lower())
    return cv2.rotate(frame, CV_ROTATE[deg]) if deg else frame


def contain(img: Image.Image, bw: float, bh: float) -> Image.Image:
    r = min(bw / img.width, bh / img.height)
    return img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))), Image.Resampling.LANCZOS)


def cover(img: Image.Image, w: int, h: int) -> Image.Image:
    r = max(w / img.width, h / img.height)
    im = img.resize((max(w, round(img.width * r)), max(h, round(img.height * r))), Image.Resampling.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def soft_background(img: Image.Image, size=(CW, CH), brightness=0.5) -> Image.Image:
    small = cover(img, size[0] // 10, size[1] // 10).filter(ImageFilter.GaussianBlur(4))
    bg = small.resize(size, Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(6))
    bg = ImageEnhance.Brightness(bg).enhance(brightness)
    warm = Image.new("RGB", size, (60, 40, 25))
    return Image.blend(bg, warm, 0.18)


def rounded_mask(size, radius=18) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def paste_print(canvas: Image.Image, img: Image.Image, xy: tuple[int, int]) -> None:
    """Paste with rounded corners and a soft drop shadow."""
    mask = rounded_mask(img.size)
    shadow = Image.new("L", canvas.size, 0)
    shadow.paste(mask, (xy[0], xy[1] + 14))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26)).point(lambda v: int(v * 0.6))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), shadow)
    canvas.paste(img, xy, mask)


def draw_text_block(canvas: Image.Image, lines: list[tuple], center_y: float | None = None) -> None:
    """lines: (text, font, fill, gap_after). text '---' draws a short gold rule."""
    draw = ImageDraw.Draw(canvas)
    boxes = [draw.textbbox((0, 0), t, font=f) if t != "---" else (0, 0, 140, 3) for t, f, _, _ in lines]
    heights = [b[3] - b[1] for b in boxes]
    total = sum(heights) + sum(g for *_, g in lines[:-1])
    y = (center_y if center_y is not None else canvas.height / 2) - total / 2

    shadow = Image.new("L", canvas.size, 0)
    sd = ImageDraw.Draw(shadow)
    ops = []
    for (t, f, fill, gap), b, h in zip(lines, boxes, heights):
        x = (canvas.width - (b[2] - b[0])) / 2 - b[0]
        if t == "---":
            ops.append(("rule", (x, y, x + 140, y + 2), fill))
        else:
            sd.text((x, y - b[1] + 4), t, font=f, fill=255)
            ops.append(("text", (x, y - b[1]), t, f, fill))
        y += h + gap
    shadow = shadow.filter(ImageFilter.GaussianBlur(12)).point(lambda v: int(v * 0.65))
    canvas.paste(Image.new("RGB", canvas.size, (0, 0, 0)), (0, 0), shadow)
    for op in ops:
        if op[0] == "rule":
            draw.rectangle(op[1], fill=op[2])
        else:
            draw.text(op[1], op[2], font=op[3], fill=op[4])


def caption_overlay(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Small date caption as (rgb float, alpha float) arrays."""
    f = serif_italic(44)
    pad = 48
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    b = tmp.textbbox((0, 0), text, font=f)
    w, h = b[2] - b[0] + pad * 2, b[3] - b[1] + pad * 2
    alpha = Image.new("L", (w, h), 0)
    ImageDraw.Draw(alpha).text((pad - b[0], pad - b[1] + 3), text, font=f, fill=255)
    # Wide dark halo keeps the caption readable over bright photos
    halo = alpha.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(14))
    shadow = halo.point(lambda v: min(255, int(v * 1.6)))
    rgb = Image.new("RGB", (w, h), (0, 0, 0))
    rgb.paste(Image.new("RGB", (w, h), CREAM), (0, 0), alpha)
    a = np.maximum(np.asarray(alpha, np.float32), np.asarray(shadow, np.float32) * 0.6) / 255.0
    return np.asarray(rgb, np.float32), a[..., None]


def nice_date(d: datetime) -> str:
    return f"{d.day} {d:%B %Y}"


def pair_caption(a: datetime, b: datetime) -> str:
    if a.date() == b.date():
        return nice_date(a)
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day} – {b.day} {a:%B %Y}"
    return f"{nice_date(a)}  ·  {nice_date(b)}"


# ---------- segments ----------

class Segment:
    duration: float
    caption: str | None = None

    def __init__(self) -> None:
        self._cap = None

    def prepare(self) -> None: ...

    def release(self) -> None: ...

    def raw_frame(self, t: float) -> np.ndarray:
        raise NotImplementedError

    def frame(self, t: float) -> np.ndarray:
        out = self.raw_frame(t)
        if self.caption:
            if self._cap is None:
                self._cap = caption_overlay(self.caption)
            rgb, a = self._cap
            k = min(1.0, max(0.0, (t - 0.5) / 0.6), max(0.0, (self.duration - 0.4 - t) / 0.6))
            if k > 0:
                h, w = a.shape[:2]
                x, y = 70, H - 60 - h
                region = out[y : y + h, x : x + w].astype(np.float32)
                ak = a * k
                out[y : y + h, x : x + w] = (region * (1 - ak) + rgb * ak).astype(np.uint8)
        return out


class Slide(Segment):
    """A static composition animated with a slow Ken Burns zoom/pan."""

    PANS = [(0.5, 0.5), (0.35, 0.6), (0.65, 0.4), (0.5, 0.35), (0.4, 0.45), (0.6, 0.6)]

    def __init__(self, build, duration: float, index: int, caption: str | None = None) -> None:
        super().__init__()
        self.build, self.duration, self.index, self.caption = build, duration, index, caption
        self.canvas: np.ndarray | None = None

    def prepare(self) -> None:
        if self.canvas is None:
            self.canvas = np.ascontiguousarray(np.asarray(self.build(), np.uint8))

    def release(self) -> None:
        self.canvas = None

    def raw_frame(self, t: float) -> np.ndarray:
        self.prepare()
        u = min(1.0, max(0.0, t / self.duration))
        e = u * u * (3 - 2 * u)
        zoom_in = self.index % 2 == 0
        s = OVER - (OVER - 1) * e if zoom_in else 1 + (OVER - 1) * e
        px, py = self.PANS[self.index % len(self.PANS)]
        cx = (CW - W * s) * (0.5 + (px - 0.5) * e)
        cy = (CH - H * s) * (0.5 + (py - 0.5) * e)
        m = np.float32([[1 / s, 0, -cx / s], [0, 1 / s, -cy / s]])
        return cv2.warpAffine(self.canvas, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


class VideoClip(Segment):
    def __init__(self, path: Path, duration_s: float | None, caption: str | None) -> None:
        super().__init__()
        self.path, self.caption = path, caption
        self.duration = min(VIDEO_MAX_S, duration_s or VIDEO_MAX_S)
        self.cap = None

    def prepare(self) -> None:
        if self.cap is not None:
            return
        self.cap = cv2.VideoCapture(str(self.path))
        self.src_fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        ok, first = self.cap.read()
        if not ok:
            raise RuntimeError(f"Cannot read video {self.path}")
        rgb = rotate_frame(cv2.cvtColor(first, cv2.COLOR_BGR2RGB), self.path)
        self.bg = np.asarray(soft_background(Image.fromarray(rgb), (W, H), 0.45), np.uint8)
        fh, fw = rgb.shape[:2]
        r = min(W * 0.9 / fw, H * 0.86 / fh)
        self.fw, self.fh = round(fw * r), round(fh * r)
        self.x, self.y = (W - self.fw) // 2, (H - self.fh) // 2
        self.mask = np.asarray(rounded_mask((self.fw, self.fh)), np.float32)[..., None] / 255.0
        self.pos, self.last = 0, rgb

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def raw_frame(self, t: float) -> np.ndarray:
        self.prepare()
        want = int(t * self.src_fps)
        while self.pos < want:
            ok, fr = self.cap.read()
            if not ok:
                break
            self.last = rotate_frame(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB), self.path)
            self.pos += 1
        out = self.bg.copy()
        fg = cv2.resize(self.last, (self.fw, self.fh), interpolation=cv2.INTER_AREA).astype(np.float32)
        region = out[self.y : self.y + self.fh, self.x : self.x + self.fw].astype(np.float32)
        out[self.y : self.y + self.fh, self.x : self.x + self.fw] = (
            region * (1 - self.mask) + fg * self.mask
        ).astype(np.uint8)
        return out


# ---------- compositions ----------

def build_single(path: Path):
    def build():
        img = load_photo(path)
        canvas = soft_background(img)
        fg = contain(img, CW * 0.84, CH * 0.84)
        paste_print(canvas, fg, ((CW - fg.width) // 2, (CH - fg.height) // 2))
        return canvas

    return build


def build_pair(a: Path, b: Path):
    def build():
        ia, ib = load_photo(a), load_photo(b)
        canvas = soft_background(ia)
        gap = 44
        bw, bh = (CW * 0.84 - gap) / 2, CH * 0.84
        fa, fb = contain(ia, bw, bh), contain(ib, bw, bh)
        total = fa.width + gap + fb.width
        x = (CW - total) // 2
        paste_print(canvas, fa, (x, (CH - fa.height) // 2))
        paste_print(canvas, fb, (x + fa.width + gap, (CH - fb.height) // 2))
        return canvas

    return build


def build_card(bg_path: Path | None, lines: list[tuple], brightness=0.42):
    def build():
        if bg_path:
            canvas = soft_background(load_photo(bg_path, 800), brightness=brightness)
        else:
            canvas = Image.new("RGB", (CW, CH), (40, 34, 30))
        draw_text_block(canvas, lines)
        return canvas

    return build


# ---------- main ----------

def collect(folder_id: int | None) -> list[tuple[Media, Path]]:
    with db.SessionLocal() as s:
        q = select(Media, SourceFolder.path).join(SourceFolder, SourceFolder.id == Media.folder_id)
        q = q.where(~Media.missing, Media.error.is_(None))
        if folder_id is not None:
            q = q.where(Media.folder_id == folder_id)
        rows = s.execute(q.order_by(Media.taken_at, Media.id)).all()
    return [(m, Path(root) / m.rel_path) for m, root in rows]


def _signature(media_id: int) -> np.ndarray | None:
    """Tiny grayscale fingerprint from the app's own thumbnail."""
    p = thumb_path(media_id)
    if not p.is_file():
        return None
    with Image.open(p) as im:
        return np.asarray(im.convert("L").resize((24, 24), Image.Resampling.BILINEAR), np.float32)


def drop_near_duplicates(items: list[tuple[Media, Path]], window_s=120, max_diff=12.0):
    """Skip photos that look almost identical to the previous one taken minutes earlier."""
    kept: list[tuple[Media, Path]] = []
    prev_sig, prev_time = None, None
    for m, p in items:
        sig = _signature(m.id) if m.kind == "photo" else None
        if (
            sig is not None and prev_sig is not None
            and (m.taken_at - prev_time).total_seconds() <= window_s
            and float(np.mean(np.abs(sig - prev_sig))) < max_diff
        ):
            print(f"  skipping near-duplicate {m.filename}")
            continue
        kept.append((m, p))
        if sig is not None:
            prev_sig, prev_time = sig, m.taken_at
    return kept


def plan(items: list[tuple[Media, Path]]) -> list[Segment]:
    years = [m.taken_at.year for m, _ in items]
    per_year = Counter(years)
    first_photo = next((p for m, p in items if m.kind == "photo"), None)
    span = f"{years[0]} – {years[-1]}" if years[0] != years[-1] else str(years[0])

    segs: list[Segment] = [
        Slide(
            build_card(first_photo, [
                ("Our Family Memories", serif(118), CREAM, 34),
                ("---", None, GOLD, 34),
                (span, serif_italic(56), GOLD, 22),
                (f"{len(items)} moments", sans(30), MUTED, 0),
            ], brightness=0.38),
            TITLE_S, 0,
        )
    ]
    idx, i, year = 1, 0, None
    while i < len(items):
        m, p = items[i]
        if m.taken_at.year != year:
            year = m.taken_at.year
            bg = next((pp for mm, pp in items[i:] if mm.kind == "photo" and mm.taken_at.year == year), None)
            n = per_year[year]
            segs.append(Slide(build_card(bg, [
                (str(year), serif(210), CREAM, 18),
                (f"{n} moment{'s' if n != 1 else ''}", serif_italic(48), GOLD, 0),
            ]), YEAR_S, idx))
            idx += 1

        if m.kind == "video":
            segs.append(VideoClip(p, m.duration_s, nice_date(m.taken_at)))
            i += 1
            continue

        portrait = (m.height or 0) > (m.width or 0)
        if portrait and i + 1 < len(items):
            m2, p2 = items[i + 1]
            if m2.kind == "photo" and (m2.height or 0) > (m2.width or 0) and m2.taken_at.year == year:
                segs.append(Slide(build_pair(p, p2), PAIR_S, idx, pair_caption(m.taken_at, m2.taken_at)))
                idx += 1
                i += 2
                continue
        segs.append(Slide(build_single(p), PHOTO_S, idx, nice_date(m.taken_at)))
        idx += 1
        i += 1

    last_photo = next((p for m, p in reversed(items) if m.kind == "photo"), None)
    segs.append(Slide(build_card(last_photo, [
        ("Every moment, kept.", serif(96), CREAM, 30),
        ("---", None, GOLD, 30),
        ("Family Memories", serif_italic(44), GOLD, 0),
    ], brightness=0.35), END_S, idx))
    return segs


def render(segs: list[Segment], out: Path, music: Path | None) -> float:
    starts, t = [], 0.0
    for seg in segs:
        starts.append(t)
        t += seg.duration - FADE_S
    total = starts[-1] + segs[-1].duration
    n_frames = int(total * FPS)

    out_params = ["-crf", "19", "-preset", "medium", "-movflags", "+faststart"]
    if music:
        out_params += ["-shortest", "-af", f"afade=t=in:d=1.5,afade=t=out:st={max(0, total - 3):.2f}:d=3"]
    writer = imageio_ffmpeg.write_frames(
        str(out), (W, H), fps=FPS, codec="libx264", quality=None, macro_block_size=8,
        output_params=out_params, audio_path=str(music) if music else None,
        audio_codec="aac" if music else None,
    )
    writer.send(None)

    lo, last_pct = 0, -1
    try:
        for f in range(n_frames):
            T = f / FPS
            while lo < len(segs) and starts[lo] + segs[lo].duration <= T:
                segs[lo].release()
                lo += 1
            active = [k for k in (lo, lo + 1) if k < len(segs) and starts[k] <= T < starts[k] + segs[k].duration]
            frames = [segs[k].frame(T - starts[k]) for k in active]
            if len(frames) == 2:
                a = (T - starts[active[1]]) / FADE_S
                frame = cv2.addWeighted(frames[0], 1 - a, frames[1], a, 0)
            else:
                frame = frames[0]
            k = min(1.0, T / 0.8, (total - T) / 1.5)
            if k < 1:
                frame = (frame.astype(np.float32) * max(k, 0)).astype(np.uint8)
            writer.send(np.ascontiguousarray(frame).tobytes())

            pct = (f + 1) * 100 // n_frames
            if pct % 10 == 0 and pct != last_pct:
                print(f"  {pct}%", flush=True)
                last_pct = pct
    finally:
        writer.close()
        for seg in segs:
            seg.release()
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder-id", type=int)
    ap.add_argument("--music", type=Path, help="optional mp3/m4a/wav to use as soundtrack")
    ap.add_argument("--rotate", action="append", default=[], metavar="NAME=DEG",
                    help="rotate a sideways file clockwise by 90/180/270, e.g. VID123.mp4=270")
    ap.add_argument("--keep-duplicates", action="store_true", help="include near-identical burst shots")
    args = ap.parse_args()

    for spec in args.rotate:
        name, _, deg = spec.rpartition("=")
        if not name or deg not in ("90", "180", "270"):
            print(f"Bad --rotate value: {spec} (use NAME=90|180|270)")
            return 1
        ROTATE[name.lower()] = int(deg)

    data = safety.set_data_dir(default_data_dir())
    db.init_db(data)
    items = collect(args.folder_id)
    if not args.keep_duplicates:
        items = drop_near_duplicates(items)
    if not items:
        print("Library is empty. Scan a folder first.")
        return 1
    if args.music and not args.music.is_file():
        print(f"Music file not found: {args.music}")
        return 1

    out = safety.check_writable(data / "exports" / f"memories-{datetime.now():%Y%m%d-%H%M%S}.mp4")
    safety.safe_mkdir(out.parent)

    segs = plan(items)
    print(f"Rendering {len(items)} items as {len(segs)} scenes -> {out}")
    total = render(segs, out, args.music)
    print(f"Done: {total:.0f}s video, {out.stat().st_size / 1e6:.1f} MB\n{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
