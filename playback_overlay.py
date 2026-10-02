import machine
from machine import Pin


BLACK = 0x0000
WHITE = 0xFFFF
GREEN = 0x07E0
TRACK = 0x2945

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


class Overlay:
    """Direct-SPI footer renderer that does not reset the LCD."""

    def __init__(self):
        self.spi = machine.SPI(1, baudrate=40_000_000, polarity=0, phase=0)
        self.dc = Pin("PB0", Pin.OUT, value=1)
        self.cs = Pin("PC4", Pin.OUT, value=1)
        self.cmd = bytearray(1)
        self.coords = bytearray(4)
        # Keep this small so decode still has a contiguous ~4609-byte hole.
        self.row = bytearray(108)
        self.row_mv = memoryview(self.row)
        self._fill_color = -1
        self._last_label = ""
        self._last_filled = -1
        self._last_playing = None

    def _write(self, command, data=None):
        self.cs(0)
        self.dc(0)
        self.cmd[0] = command
        self.spi.write(self.cmd)
        if data is not None:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _window(self, x0, y0, x1, y1):
        b = self.coords
        b[0], b[1], b[2], b[3] = x0 >> 8, x0 & 255, x1 >> 8, x1 & 255
        self._write(0x2A, b)
        b[0], b[1], b[2], b[3] = y0 >> 8, y0 & 255, y1 >> 8, y1 & 255
        self._write(0x2B, b)
        self._write(0x2C)

    def _prepare_row(self, color, width):
        if color != self._fill_color:
            hi = color >> 8
            lo = color & 255
            row = self.row
            for pos in range(0, len(row), 2):
                row[pos] = hi
                row[pos + 1] = lo
            self._fill_color = color
        return self.row_mv[: width * 2]

    def fill_rect(self, x, y, width, height, color):
        if width <= 0 or height <= 0:
            return
        data = self._prepare_row(color, width if width <= 108 else 108)
        max_w = len(data) // 2
        self._window(x, y, x + width - 1, y + height - 1)
        self.cs(0)
        self.dc(1)
        for _ in range(height):
            remaining = width
            while remaining > 0:
                n = remaining if remaining <= max_w else max_w
                self.spi.write(self.row_mv[: n * 2])
                remaining -= n
        self.cs(1)

    def _blit_glyph_row(self, x, y, bits, color):
        # One horizontal 5px strip instead of up to 5 pixel transactions.
        hi = color >> 8
        lo = color & 255
        row = self.row
        for column in range(5):
            on = bits & (0x10 >> column)
            row[column * 2] = hi if on else 0
            row[column * 2 + 1] = lo if on else 0
        self._window(x, y, x + 4, y)
        self.cs(0)
        self.dc(1)
        self.spi.write(self.row_mv[:10])
        self.cs(1)
        self._fill_color = -1

    def text(self, x, y, value, color):
        for char in value:
            if "0" <= char <= "9":
                rows = _DIGITS[ord(char) - 48]
            elif char == ":":
                rows = _COLON
            else:
                rows = _DASH
            for row_index in range(7):
                self._blit_glyph_row(x, y + row_index, rows[row_index], color)
            x += 6

    def state(self, playing):
        if playing == self._last_playing:
            return
        self._last_playing = playing
        self.fill_rect(7, 208, 18, 18, BLACK)
        if playing:
            # Simple play triangle proxy: small green block (fast).
            self.fill_rect(12, 212, 8, 10, GREEN)
        else:
            self.fill_rect(11, 212, 10, 10, WHITE)

    def progress(self, elapsed_ms, duration_ms, playing):
        duration_ms = max(1, duration_ms)
        elapsed_ms = min(duration_ms, max(0, elapsed_ms))
        self.state(playing)

        filled = (216 * elapsed_ms) // duration_ms
        if filled != self._last_filled:
            if self._last_filled < 0:
                self.fill_rect(34, 218, 216, 7, TRACK)
                if filled:
                    self.fill_rect(34, 218, filled, 7, GREEN)
            elif filled > self._last_filled:
                # Only paint the newly filled slice — cheap during playback.
                self.fill_rect(
                    34 + self._last_filled,
                    218,
                    filled - self._last_filled,
                    7,
                    GREEN,
                )
            else:
                self.fill_rect(34, 218, 216, 7, TRACK)
                if filled:
                    self.fill_rect(34, 218, filled, 7, GREEN)
            self._last_filled = filled

        remaining = (duration_ms - elapsed_ms + 999) // 1000
        minutes = min(99, remaining // 60)
        seconds = remaining % 60
        label = "-%02d:%02d" % (minutes, seconds)
        if label != self._last_label:
            self.fill_rect(258, 210, 38, 9, BLACK)
            self.text(258, 211, label, WHITE)
            self._last_label = label

    def deinit(self):
        try:
            self.spi.deinit()
        except Exception:
            pass
