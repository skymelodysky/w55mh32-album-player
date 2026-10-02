"""Convert songs to 16-bit stereo 44.1 kHz WAV for the W55MH32 player.

Requires ffmpeg on PATH:
    https://ffmpeg.org/download.html

Examples:
    python convert_to_wav.py --input music --output wav_out
    python convert_to_wav.py --input music/海闊天空.mp3 --output wav_out
"""

import argparse
import shutil
import subprocess
import sys
import wave
from pathlib import Path


AUDIO_EXTENSIONS = (".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".wma")
RATE = 44100
CHANNELS = 2


def require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise SystemExit(
            "ffmpeg not found on PATH.\n"
            "Install ffmpeg, then retry.\n"
            "Windows: winget install ffmpeg"
        )


def convert_one(src, dst, volume=100):
    """volume: 0..100 (baked into WAV on PC — board stays smooth)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-acodec",
        "pcm_s16le",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(RATE),
    ]
    if volume != 100:
        # ffmpeg volume=1.0 is full; 50 -> 0.5
        cmd.extend(["-filter:a", "volume=%s" % (volume / 100.0)])
    cmd.append(str(dst))
    print("Converting:", src.name, "->", dst.name, "vol:", volume)
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace")
        raise SystemExit("ffmpeg failed for %s\n%s" % (src, err[-800:]))

    with wave.open(str(dst), "rb") as wav:
        if wav.getnchannels() != CHANNELS or wav.getframerate() != RATE:
            raise SystemExit("Unexpected WAV format: %s" % dst)
        if wav.getsampwidth() != 2:
            raise SystemExit("WAV must be 16-bit: %s" % dst)
        seconds = wav.getnframes() / float(RATE)
    print("  OK %.1f s, 16-bit stereo %d Hz" % (seconds, RATE))
    return int(round(seconds * 1000))


def collect_sources(input_path):
    input_path = Path(input_path)
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise SystemExit("Input not found: %s" % input_path)
    files = [
        path
        for path in sorted(input_path.iterdir(), key=lambda p: p.name.casefold())
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    ]
    if not files:
        raise SystemExit("No audio files in %s" % input_path)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Convert audio to PCM WAV for the board player"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("music"),
        help="Folder or single audio file (default: music)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("wav_out"),
        help="Output folder (default: wav_out)",
    )
    parser.add_argument(
        "--ascii-names",
        action="store_true",
        help="Write 000.wav, 001.wav, ... (board-safe names)",
    )
    parser.add_argument(
        "--volume",
        type=int,
        default=100,
        help="Output loudness 0..100 (default 100). Applied on PC.",
    )
    args = parser.parse_args()

    require_ffmpeg()
    vol = args.volume
    if vol < 0:
        vol = 0
    elif vol > 100:
        vol = 100
    sources = collect_sources(args.input)
    args.output.mkdir(parents=True, exist_ok=True)

    for index, src in enumerate(sources):
        if args.ascii_names:
            name = "%03d.wav" % index
        else:
            name = src.stem + ".wav"
        convert_one(src, args.output / name, vol)

    print("Done. Copy WAV files to SD /music/ (or run prepare_media.py).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
