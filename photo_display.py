import gc

import machine
from machine import Pin

import st7789_min


SCREEN_W = 320
SCREEN_H = 240

_DIGITS = (
    (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    (0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E),
    (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    (0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E),
    (0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E),
)
_COLON = (0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00)
_DASH = (0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00)
WHITE = 0xFFFF
GREEN = 0x07E0
TRACK = 0x2945


def _glyph(display, x, y, rows, color):
    for row_index in range(7):
        bits = rows[row_index]
        for column in range(5):
            if bits & (0x10 >> column):
                display.pixel(x + column, y + row_index, color)


def _text(display, x, y, value, color):
    for char in value:
        if "0" <= char <= "9":
            rows = _DIGITS[ord(char) - 48]
        elif char == ":":
            rows = _COLON
        else:
            rows = _DASH
        _glyph(display, x, y, rows, color)
        x += 6


def _fill(display, buf, x, y, w, h, color):
    hi = color >> 8
    lo = color & 255
    needed = w * 2
    for i in range(0, needed, 2):
        buf[i] = hi
        buf[i + 1] = lo
    line = memoryview(buf)[:needed]
    for row in range(h):
        display.blit_buffer(line, x, y + row, w, 1)


def show(path, duration_ms=0):
    """Draw one converted RGB565 photo plus a static footer/time bar."""
    spi = machine.SPI(1, baudrate=40_000_000, polarity=0, phase=0)
    display = st7789_min.ST7789(
        spi,
        240,
        320,
        reset=Pin("PC5", Pin.OUT),
        dc=Pin("PB0", Pin.OUT),
        cs=Pin("PC4", Pin.OUT),
        backlight=Pin("PB1", Pin.OUT),
        rotation=1,
    )
    display.inversion_mode(False)
    display.fill(st7789_min.BLACK)

    with open(path, "rb") as f:
        header = f.read(4)
        if len(header) != 4:
            raise ValueError("invalid RGB565 file")

        width = (header[0] << 8) | header[1]
        height = (header[2] << 8) | header[3]
        if (
            width <= 0
            or height <= 0
            or width > SCREEN_W
            or height > SCREEN_H
        ):
            raise ValueError("invalid image size")

        x = (SCREEN_W - width) // 2
        y = (SCREEN_H - height) // 2
        row = bytearray(width * 2)

        for line in range(height):
            count = f.readinto(row)
            if count != len(row):
                break
            display.blit_buffer(row, x, y + line, width, 1)

    # Static footer: play ▶, empty progress track, total duration.
    footer = bytearray(SCREEN_W * 2)
    _fill(display, footer, 0, 208, SCREEN_W, SCREEN_H - 208, 0x0000)
    x0, y0 = 11, 211
    for dy in range(12):
        dist = dy - 5
        if dist < 0:
            dist = -dist
        width = 6 - dist
        if width > 0:
            _fill(display, footer, x0, y0 + dy, width, 1, GREEN)
    _fill(display, footer, 34, 218, 216, 7, TRACK)

    if duration_ms > 0:
        total_s = (duration_ms + 999) // 1000
        label = "-%02d:%02d" % (min(99, total_s // 60), total_s % 60)
        _text(display, 258, 211, label, WHITE)

    print("photo shown:", path, width, "x", height)

    row = None
    footer = None
    display = None
    try:
        spi.deinit()
    except Exception:
        pass
    spi = None
    gc.collect()
