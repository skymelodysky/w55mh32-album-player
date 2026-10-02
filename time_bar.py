"""Tiny SPI time-bar updater. Allocates almost nothing; safe to call rarely."""

import machine
from machine import Pin


GREEN = 0x07E0
TRACK = 0x2945
WHITE = 0xFFFF
BLACK = 0x0000

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

_cmd = bytearray(1)
_coords = bytearray(4)
_row = bytearray(108)
_row_mv = memoryview(_row)
# 6 chars * 6px * 7 rows * 2 bytes
_label = bytearray(504)
_last_filled = -1
_last_label = ""
_last_playing = None


def reset():
    global _last_filled, _last_label, _last_playing
    _last_filled = -1
    _last_label = ""
    _last_playing = None


def _write(spi, dc, cs, command, data=None):
    cs(0)
    dc(0)
    _cmd[0] = command
    spi.write(_cmd)
    if data is not None:
        dc(1)
        spi.write(data)
    cs(1)


def _window(spi, dc, cs, x0, y0, x1, y1):
    b = _coords
    b[0], b[1], b[2], b[3] = x0 >> 8, x0 & 255, x1 >> 8, x1 & 255
    _write(spi, dc, cs, 0x2A, b)
    b[0], b[1], b[2], b[3] = y0 >> 8, y0 & 255, y1 >> 8, y1 & 255
    _write(spi, dc, cs, 0x2B, b)
    _write(spi, dc, cs, 0x2C)


def _fill(spi, dc, cs, x, y, width, height, color):
    if width <= 0 or height <= 0:
        return
    hi = color >> 8
    lo = color & 255
    max_w = len(_row) // 2
    for pos in range(0, len(_row), 2):
        _row[pos] = hi
        _row[pos + 1] = lo
    _window(spi, dc, cs, x, y, x + width - 1, y + height - 1)
    cs(0)
    dc(1)
    for _ in range(height):
        left = width
        while left > 0:
            n = left if left <= max_w else max_w
            spi.write(_row_mv[: n * 2])
            left -= n
    cs(1)


def _glyph_row(spi, dc, cs, x, y, bits, color):
    hi = color >> 8
    lo = color & 255
    for column in range(5):
        on = bits & (0x10 >> column)
        _row[column * 2] = hi if on else 0
        _row[column * 2 + 1] = lo if on else 0
    _window(spi, dc, cs, x, y, x + 4, y)
    cs(0)
    dc(1)
    spi.write(_row_mv[:10])
    cs(1)


def _text_blit(spi, dc, cs, x, y, value, color):
    # One windowed blit for the whole label — much faster than per-pixel SPI.
    width = len(value) * 6
    height = 7
    needed = width * height * 2
    buf = _label
    for i in range(needed):
        buf[i] = 0
    hi = color >> 8
    lo = color & 255
    for index, char in enumerate(value):
        if "0" <= char <= "9":
            rows = _DIGITS[ord(char) - 48]
        elif char == ":":
            rows = _COLON
        else:
            rows = _DASH
        ox = index * 6
        for row_index in range(7):
            bits = rows[row_index]
            base = (row_index * width + ox) * 2
            for column in range(5):
                if bits & (0x10 >> column):
                    pos = base + column * 2
                    buf[pos] = hi
                    buf[pos + 1] = lo
    _window(spi, dc, cs, x, y, x + width - 1, y + height - 1)
    cs(0)
    dc(1)
    spi.write(memoryview(buf)[:needed])
    cs(1)


def _draw_state(spi, dc, cs, playing):
    # Clear icon area, then draw ▶ or ❚❚
    _fill(spi, dc, cs, 7, 208, 18, 18, BLACK)
    if playing:
        # Play triangle pointing right
        x0, y0 = 11, 211
        for dy in range(12):
            dist = dy - 5
            if dist < 0:
                dist = -dist
            width = 6 - dist
            if width > 0:
                _fill(spi, dc, cs, x0, y0 + dy, width, 1, GREEN)
    else:
        # Pause: two vertical bars
        _fill(spi, dc, cs, 11, 212, 3, 10, WHITE)
        _fill(spi, dc, cs, 17, 212, 3, 10, WHITE)


def draw(elapsed_ms, duration_ms, playing=True):
    """Update play/stop, progress fill, remaining time."""
    global _last_filled, _last_label, _last_playing

    duration_ms = max(1, duration_ms)
    elapsed_ms = min(duration_ms, max(0, elapsed_ms))
    filled = (216 * elapsed_ms) // duration_ms
    remaining = (duration_ms - elapsed_ms + 999) // 1000
    label = "-%02d:%02d" % (min(99, remaining // 60), remaining % 60)

    if (
        filled == _last_filled
        and label == _last_label
        and playing == _last_playing
    ):
        return

    spi = machine.SPI(1, baudrate=40_000_000, polarity=0, phase=0)
    dc = Pin("PB0", Pin.OUT, value=1)
    cs = Pin("PC4", Pin.OUT, value=1)
    try:
        if playing != _last_playing:
            _draw_state(spi, dc, cs, playing)
            _last_playing = playing

        if filled != _last_filled:
            if _last_filled < 0:
                _fill(spi, dc, cs, 34, 218, 216, 7, TRACK)
                if filled:
                    _fill(spi, dc, cs, 34, 218, filled, 7, GREEN)
            elif filled > _last_filled:
                _fill(
                    spi,
                    dc,
                    cs,
                    34 + _last_filled,
                    218,
                    filled - _last_filled,
                    7,
                    GREEN,
                )
            else:
                _fill(spi, dc, cs, 34, 218, 216, 7, TRACK)
                if filled:
                    _fill(spi, dc, cs, 34, 218, filled, 7, GREEN)
            _last_filled = filled

        if label != _last_label:
            _fill(spi, dc, cs, 258, 210, 38, 9, BLACK)
            _text_blit(spi, dc, cs, 258, 211, label, WHITE)
            _last_label = label
    finally:
        try:
            spi.deinit()
        except Exception:
            pass
