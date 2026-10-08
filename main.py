"""W55MH32-ADK landscape photo + WAV player."""

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

# Use a list so release can drop the only reference with pop().
_holes = []


def unload(name):
    try:
        del sys.modules[name]
    except (KeyError, AttributeError):
        pass
    gc.collect()


def hard_gc():
    gc.collect()
    time.sleep_ms(20)
    gc.collect()


def reserve_audio_hole():
    release_audio_hole()
    for size in (AUDIO_HOLE_SIZE, 16384, 12288):
        try:
            _holes.append(bytearray(size))
            print("audio hole:", size, "free:", gc.mem_free())
            return
        except MemoryError:
            pass
    print("audio hole: none", "free:", gc.mem_free())


def release_audio_hole():
    freed = 0
    while _holes:
        block = _holes.pop()
        freed += len(block)
        block = None
    hard_gc()
    if freed:
        print("hole freed:", freed, "free:", gc.mem_free())


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
        hard_gc()
        print("free before audio:", gc.mem_free())


def play_song(item):
    path = MUSIC_DIR + item["music"]
    result = "error"

    before = gc.mem_free()
    release_audio_hole()
    hard_gc()
    after = gc.mem_free()
    print("free after hole release:", after, "delta:", after - before)
    # If hole did not come back, scrub modules again before I2S.
    if after - before < 4000:
        unload("audio_player")
        unload("time_bar")
        unload("playback_overlay")
        unload("photo_display")
        unload("st7789_min")
        hard_gc()
        print("extra cleanup free:", gc.mem_free())

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
            hard_gc()
            print("free after audio:", gc.mem_free())

        if result in ("finished", "next"):
            break
        print("reload song:", path, "attempt", attempt + 1)
        hard_gc()
        time.sleep_ms(80)

    # Do NOT reserve here — heap is still warm/fragmented.
    # Reserve again only right before the next show_screen.
    return result


def main():
    mount_sd()
    try:
        playlist = load_playlist()
    except Exception as exc:
        print("playlist error:", exc)
        print(
            "Run prepare_media.py and copy playlist.json + music/*.wav + ui to SD."
        )
        return

    if not playlist:
        print("playlist.json has no playable entries")
        return

    print("tracks:", len(playlist))
    index = 0
    while True:
        item = playlist[index]
        print("track:", item.get("title", item["music"]))
        hard_gc()
        reserve_audio_hole()
        show_screen(item)
        result = play_song(item)
        if result not in ("finished", "next"):
            print("skip track after failed play")
        index = (index + 1) % len(playlist)


main()

