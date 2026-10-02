"""Prepare SD-card assets for the W55MH32 landscape WAV music player.

Example:
    pip install pillow
    winget install ffmpeg
    python prepare_media.py --music music --photo photo --output prepared_sd

Input files are paired by basename:
    music/海闊天空.mp3
    photo/海闊天空.png

Output:
    prepared_sd/playlist.json
    prepared_sd/music/000.wav
    prepared_sd/ui/000.rgb565
"""

import argparse
import json
import shutil
import struct
import subprocess
import urllib.request
import wave
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as exc:
    raise SystemExit("Install Pillow first: pip install pillow") from exc


AUDIO_EXTENSIONS = (".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".wma")
WAV_RATE = 44100
WAV_CHANNELS = 2


WIDTH = 320
HEIGHT = 240
FOOTER_TOP = 202
PHOTO_BOX = (4, 4, 198, 198)
TITLE_BOX = (207, 12, 314, 194)
FONT_URL = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/"
    "Sans/OTF/TraditionalChinese/NotoSansCJKtc-Regular.otf"
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def find_font(explicit_path, cache_dir):
    if explicit_path:
        path = Path(explicit_path)
        if not path.is_file():
            raise SystemExit("Font not found: %s" % path)
        return path

    cached = cache_dir / "NotoSansCJKtc-Regular.otf"
    if not cached.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        print("Downloading Noto Sans Traditional Chinese once...")
        try:
            urllib.request.urlretrieve(FONT_URL, cached)
        except Exception as exc:
            raise SystemExit(
                "Could not download Noto Sans TC. Download "
                "NotoSansCJKtc-Regular.otf and pass --font PATH.\n%s" % exc
            )
    return cached


def find_photos(folder):
    photos = {}
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            photos[path.stem.casefold()] = path
    return photos


def wrap_characters(draw, text, font, max_width):
    lines = []
    current = ""
    for char in text:
        trial = current + char
        box = draw.textbbox((0, 0), trial, font=font)
        if current and box[2] - box[0] > max_width:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = trial
    if current:
        lines.append(current.rstrip())
    return lines


def fit_title(draw, title, font_path, box):
    max_width = box[2] - box[0]
    max_height = box[3] - box[1]
    for size in range(25, 13, -1):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap_characters(draw, title, font, max_width)
        spacing = max(3, size // 5)
        line_height = size + spacing
        if len(lines) * line_height <= max_height:
            return font, lines, line_height

    font = ImageFont.truetype(str(font_path), 13)
    lines = wrap_characters(draw, title, font, max_width)
    max_lines = max(1, max_height // 16)
    lines = lines[:max_lines]
    if lines and len(lines) == max_lines:
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return font, lines, 16


def compose_screen(photo_path, title, font_path):
    canvas = Image.new("RGB", (WIDTH, HEIGHT), (8, 10, 14))
    photo = Image.open(photo_path)
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    photo = ImageOps.fit(
        photo,
        (PHOTO_BOX[2] - PHOTO_BOX[0], PHOTO_BOX[3] - PHOTO_BOX[1]),
        method=Image.Resampling.LANCZOS,
    )
    canvas.paste(photo, (PHOTO_BOX[0], PHOTO_BOX[1]))

    draw = ImageDraw.Draw(canvas)
    font, lines, line_height = fit_title(draw, title, font_path, TITLE_BOX)
    total_height = len(lines) * line_height
    y = TITLE_BOX[1] + max(0, (TITLE_BOX[3] - TITLE_BOX[1] - total_height) // 2)
    for line in lines:
        line_width = draw.textlength(line, font=font)
        x = TITLE_BOX[0] + max(0, (TITLE_BOX[2] - TITLE_BOX[0] - line_width) / 2)
        draw.text((x, y), line, font=font, fill=(244, 246, 250))
        y += line_height

    # Footer is deliberately simple; the board redraws this area while playing.
    draw.rectangle((0, FOOTER_TOP, WIDTH - 1, HEIGHT - 1), fill=(5, 7, 10))
    draw.rounded_rectangle((34, 218, 250, 225), radius=3, fill=(42, 48, 58))
    return canvas


def write_rgb565(image, destination):
    image = image.convert("RGB")
    width, height = image.size
    out = bytearray(width * height * 2)
    pos = 0
    for r, g, b in image.getdata():
        color = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[pos] = color >> 8
        out[pos + 1] = color & 0xFF
        pos += 2
    with destination.open("wb") as file:
        file.write(struct.pack(">HH", width, height))
        file.write(out)


def require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise SystemExit(
            "ffmpeg not found on PATH. Install it first "
            "(Windows: winget install ffmpeg)."
        )


def convert_to_wav(src, dst, volume=100):
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-acodec",
        "pcm_s16le",
        "-ac",
        str(WAV_CHANNELS),
        "-ar",
        str(WAV_RATE),
    ]
    if volume != 100:
        cmd.extend(["-filter:a", "volume=%s" % (volume / 100.0)])
    cmd.append(str(dst))
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        raise SystemExit("ffmpeg failed for %s\n%s" % (src, err[-800:]))

    with wave.open(str(dst), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        duration_ms = int(round(frames * 1000 / float(rate)))
    return duration_ms


def prepare(music_dir, photo_dir, output_dir, font_path, volume=100):
    require_ffmpeg()
    photos = find_photos(photo_dir)
    songs = sorted(
        (
            path
            for path in music_dir.iterdir()
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )
    if not songs:
        raise SystemExit("No audio files found in %s" % music_dir)

    ui_dir = output_dir / "ui"
    output_music_dir = output_dir / "music"
    ui_dir.mkdir(parents=True, exist_ok=True)
    output_music_dir.mkdir(parents=True, exist_ok=True)
    for old in output_music_dir.glob("*.mp3"):
        old.unlink()
    for old in output_music_dir.glob("*.wav"):
        old.unlink()
    for old in ui_dir.glob("*.rgb565"):
        old.unlink()
    playlist = []

    for index, song in enumerate(songs):
        photo = photos.get(song.stem.casefold())
        if photo is None:
            print("Skipping (no matching photo):", song.name)
            continue

        ui_name = "%03d.rgb565" % index
        # ASCII names: this MicroPython build cannot open Chinese filenames.
        music_name = "%03d.wav" % index
        screen = compose_screen(photo, song.stem, font_path)
        write_rgb565(screen, ui_dir / ui_name)
        duration_ms = convert_to_wav(
            song, output_music_dir / music_name, volume
        )
        playlist.append(
            {
                "title": song.stem,
                "music": music_name,
                "screen": "ui/" + ui_name,
                "duration_ms": duration_ms,
            }
        )
        print("Prepared:", song.name, "->", music_name, ui_name, duration_ms, "ms")

    if not playlist:
        raise SystemExit("No matching audio/photo basename pairs were found.")

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "playlist.json").open("w", encoding="utf-8") as file:
        json.dump(playlist, file, ensure_ascii=False, indent=2)
    print("Wrote", output_dir / "playlist.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--music", type=Path, default=Path("music"))
    parser.add_argument("--photo", type=Path, default=Path("photo"))
    parser.add_argument("--output", type=Path, default=Path("prepared_sd"))
    parser.add_argument("--font", help="Optional NotoSansCJKtc-Regular.otf path")
    parser.add_argument(
        "--volume",
        type=int,
        default=100,
        help="WAV loudness 0..100 baked on PC (default 100)",
    )
    args = parser.parse_args()

    font_path = find_font(args.font, Path(".media_cache"))
    vol = max(0, min(100, args.volume))
    prepare(args.music, args.photo, args.output, font_path, vol)


if __name__ == "__main__":
    main()
