import gc
import time

from machine import I2S, Pin


I2S_ID = 3
# Matched to the smooth WAV test (ibuf=20000).
I2S_IBUF_PREF = (20000, 16384, 12288, 8192)
READ_BUF_SIZE = 4096
WAV_HEADER = 44
BUTTON_EVERY_CHUNKS = 8
PRINT_EVERY_CHUNKS = 200
UI_EVERY_MS = 1000


def _skip_wav_header(file):
    """Skip standard PCM WAV header produced by convert_to_wav / prepare_media."""
    header = file.read(WAV_HEADER)
    if len(header) < WAV_HEADER:
        raise ValueError("WAV too short")
    if header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
        file.seek(WAV_HEADER)
        return
    file.seek(WAV_HEADER)


def play(filename, duration_ms, next_button, play_button, use_overlay=True):
    gc.collect()
    buf = bytearray(READ_BUF_SIZE)
    i2s = None
    time_bar = None
    result = "finished"

    try:
        print("audio free before I2S:", gc.mem_free())
        for ibuf in I2S_IBUF_PREF:
            try:
                i2s = I2S(
                    I2S_ID,
                    sck=Pin("PB3"),
                    ws=Pin("PA15"),
                    sd=Pin("PB5"),
                    mode=I2S.TX,
                    bits=16,
                    format=I2S.STEREO,
                    rate=44100,
                    ibuf=ibuf,
                )
                print("playing:", filename, "ibuf:", ibuf)
                break
            except MemoryError:
                i2s = None
                gc.collect()
        if i2s is None:
            print("I2S OOM")
            return "retry"

        if use_overlay:
            try:
                import time_bar as tb

                time_bar = tb
                time_bar.reset()
                time_bar.draw(0, duration_ms, True)
                print("time bar on, free:", gc.mem_free())
            except Exception as exc:
                time_bar = None
                print("time bar off:", exc)

        with open(filename, "rb") as file:
            _skip_wav_header(file)

            paused = False
            next_was_down = next_button.value() == 0
            play_was_down = play_button.value() == 0
            chunk_count = 0
            played_bytes = 0
            bytes_per_ms = 44100 * 2 * 2 // 1000  # 176
            elapsed_ms = 0
            last_ui_ms = -UI_EVERY_MS

            while True:
                if chunk_count % BUTTON_EVERY_CHUNKS == 0:
                    next_down = next_button.value() == 0
                    play_down = play_button.value() == 0
                    if next_down and not next_was_down:
                        time.sleep_ms(20)
                        if next_button.value() == 0:
                            print("next pressed")
                            result = "next"
                            while next_button.value() == 0:
                                time.sleep_ms(10)
                            break
                    if play_down and not play_was_down:
                        time.sleep_ms(20)
                        if play_button.value() == 0:
                            paused = not paused
                            print("paused" if paused else "resumed")
                            if time_bar is not None:
                                try:
                                    time_bar.draw(
                                        elapsed_ms, duration_ms, not paused
                                    )
                                except Exception:
                                    pass
                            while play_button.value() == 0:
                                time.sleep_ms(10)
                            play_was_down = False
                            next_was_down = next_button.value() == 0
                            continue
                    next_was_down = next_down
                    play_was_down = play_down

                if paused:
                    time.sleep_ms(20)
                    continue

                n = file.readinto(buf)
                if not n:
                    break

                if n == len(buf):
                    i2s.write(buf)
                else:
                    i2s.write(memoryview(buf)[:n])

                played_bytes += n
                elapsed_ms = played_bytes // max(1, bytes_per_ms)
                chunk_count += 1

                if (
                    time_bar is not None
                    and elapsed_ms - last_ui_ms >= UI_EVERY_MS
                ):
                    last_ui_ms = elapsed_ms
                    try:
                        time_bar.draw(elapsed_ms, duration_ms, True)
                    except Exception:
                        time_bar = None

                if chunk_count % PRINT_EVERY_CHUNKS == 0:
                    print(
                        "chunk:",
                        chunk_count,
                        "elapsed:",
                        elapsed_ms // 1000,
                        "free:",
                        gc.mem_free(),
                    )

            if time_bar is not None and result == "finished":
                try:
                    time_bar.draw(duration_ms, duration_ms, False)
                except Exception:
                    pass
            print("playback ended:", chunk_count, result)

    except KeyboardInterrupt:
        result = "next"
    except MemoryError as exc:
        print("audio OOM:", filename, exc)
        result = "retry"
    except Exception as exc:
        print("audio error:", filename, exc)
        result = "error"
    finally:
        if time_bar is not None:
            try:
                time_bar.reset()
            except Exception:
                pass
        time_bar = None
        if i2s is not None:
            try:
                time.sleep_ms(80)
                i2s.deinit()
                time.sleep_ms(150)
            except Exception as exc:
                print("i2s.deinit error:", exc)
            i2s = None
        buf = None
        gc.collect()
        gc.collect()

    return result

