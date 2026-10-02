"""W55MH32L-EVB landscape photo + WAV player."""

import gc
import os
import sys
import time

from machine import Pin, SDCard


PLAYLIST_PATH = "/sd/playlist.json"
MUSIC_DIR = "/sd/music/"
MAX_PLAY_RETRIES = 2
# Hold contiguous RAM through UI draw for I2S ibuf (~20000).
AUDIO_HOLE_SIZE = 22000

# User confirmed: pressed == 0 (active-low).
NEXT_BUTTON = Pin("PF13", Pin.IN, Pin.PULL_UP)
PLAY_BUTTON = Pin("PF11", Pin.IN, Pin.PULL_UP)

_audio_hole = None


def unload(name):
    try:
        del sys.modules[name]
    except (KeyError, AttributeError):
        pass
    gc.collect()


def reserve_audio_hole():
    global _audio_hole
    _audio_hole = None
    gc.collect()
    for size in (AUDIO_HOLE_SIZE, 16384, 12288):
        try:
            _audio_hole = bytearray(size)
            print("audio hole:", size)
            return
        except MemoryError:
            _audio_hole = None
    print("audio hole: none")


def release_audio_hole():
    global _audio_hole
    _audio_hole = None
    gc.collect()


def mount_sd():
    try:
        os.mount(SDCard(), "/sd")
    except OSError:
        pass


def load_playlist():
    import json

    with open(PLAYLIST_PATH, "r") as file:
        playlist = json.load(file)
    json = None
    unload("json")
    valid = []
    for item in playlist:
        if (
            "music" in item
            and "screen" in item
            and "duration_ms" in item
        ):
            valid.append(item)
    return valid


def show_screen(item):
    path = "/sd/" + item["screen"].lstrip("/")
    # Hole stays allocated so photo/UI cannot shatter the audio region.
    try:
        import photo_display

        photo_display.show(path, int(item.get("duration_ms", 0)))
        photo_display = None
    except Exception as exc:
        print("screen error:", path, exc)
    finally:
        unload("photo_display")
        unload("st7789_min")
        gc.collect()
        print("free before audio:", gc.mem_free())


def play_song(item):
    path = MUSIC_DIR + item["music"]
    result = "error"
    # Hand the contiguous block to the player before any audio allocs.
    release_audio_hole()
    time.sleep_ms(50)
    gc.collect()
    print("free after hole release:", gc.mem_free())

    for attempt in range(MAX_PLAY_RETRIES):
        try:
            import audio_player

            result = audio_player.play(
                path,
                int(item["duration_ms"]),
                NEXT_BUTTON,
                PLAY_BUTTON,
                True,
            )
            audio_player = None
        except MemoryError as exc:
            print("player OOM:", path, exc)
            result = "retry"
        except Exception as exc:
            print("player error:", path, exc)
            result = "error"
        finally:
            unload("audio_player")
            unload("time_bar")
            unload("playback_overlay")
            gc.collect()
            print("free after audio:", gc.mem_free())

        if result in ("finished", "next"):
            break
        print("reload song:", path, "attempt", attempt + 1)
        time.sleep_ms(100)
        gc.collect()

    reserve_audio_hole()
    return result


def main():
    mount_sd()
    try:
        playlist = load_playlist()
    except Exception as exc:
        print("playlist error:", exc)
        print("Run prepare_media.py and copy playlist.json + music/*.wav + ui to SD.")
        return

    if not playlist:
        print("playlist.json has no playable entries")
        return

    reserve_audio_hole()
    print("tracks:", len(playlist))
    index = 0
    while True:
        item = playlist[index]
        print("track:", item.get("title", item["music"]))
        show_screen(item)
        result = play_song(item)
        if result not in ("finished", "next"):
            print("skip track after failed play")
        index = (index + 1) % len(playlist)


main()
