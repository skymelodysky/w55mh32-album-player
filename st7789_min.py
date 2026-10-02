"""
Minimal ST7789 driver (init / fill / blit_buffer / pixel only).
Smaller than st7789py so MP3 decoder and display can coexist.
"""

import time
from micropython import const

_SWRESET = const(0x01)
_SLPOUT = const(0x11)
_COLMOD = const(0x3A)
_MADCTL = const(0x36)
_INVON = const(0x21)
_INVOFF = const(0x20)
_NORON = const(0x13)
_DISPON = const(0x29)
_CASET = const(0x2A)
_RASET = const(0x2B)
_RAMWR = const(0x2C)

# MADCTL rotation values for common panels
_ROT = (0x00, 0x60, 0xC0, 0xA0)


def color565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK = const(0x0000)
WHITE = const(0xFFFF)
CYAN = color565(0, 255, 255)
GRAY = color565(160, 160, 160)


class ST7789:
    def __init__(self, spi, width, height, reset, dc, cs, backlight=None, rotation=0):
        self.spi = spi
        self.rotation = rotation & 3
        if self.rotation & 1:
            self.width = height
            self.height = width
        else:
            self.width = width
            self.height = height
        self.reset = reset
        self.dc = dc
        self.cs = cs
        self.backlight = backlight
        self._buf1 = bytearray(1)
        self._buf4 = bytearray(4)

        if self.cs:
            self.cs.init(self.cs.OUT, value=1)
        self.dc.init(self.dc.OUT, value=0)
        if self.reset:
            self.reset.init(self.reset.OUT, value=1)
        if self.backlight:
            self.backlight.init(self.backlight.OUT, value=1)

        self._hard_reset()
        self._init(self.rotation)

    def _hard_reset(self):
        if not self.reset:
            return
        self.reset(1)
        time.sleep_ms(50)
        self.reset(0)
        time.sleep_ms(50)
        self.reset(1)
        time.sleep_ms(150)

    def _write(self, cmd, data=None):
        self.cs(0)
        self.dc(0)
        self._buf1[0] = cmd
        self.spi.write(self._buf1)
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _init(self, rotation):
        self._write(_SWRESET)
        time.sleep_ms(150)
        self._write(_SLPOUT)
        time.sleep_ms(10)
        self._write(_COLMOD, b"\x55")  # 16-bit
        self._write(_MADCTL, bytes((_ROT[rotation & 3],)))
        self._write(_INVOFF)  # inversion off (same as inversion_mode(False))
        self._write(_NORON)
        time.sleep_ms(10)
        self._write(_DISPON)
        time.sleep_ms(10)

    def inversion_mode(self, enabled):
        self._write(_INVON if enabled else _INVOFF)

    def _set_window(self, x0, y0, x1, y1):
        b = self._buf4
        b[0] = x0 >> 8
        b[1] = x0 & 0xFF
        b[2] = x1 >> 8
        b[3] = x1 & 0xFF
        self._write(_CASET, b)
        b[0] = y0 >> 8
        b[1] = y0 & 0xFF
        b[2] = y1 >> 8
        b[3] = y1 & 0xFF
        self._write(_RASET, b)
        self._write(_RAMWR)

    def blit_buffer(self, buf, x, y, w, h):
        self._set_window(x, y, x + w - 1, y + h - 1)
        self.cs(0)
        self.dc(1)
        self.spi.write(buf)
        self.cs(1)

    def fill(self, color):
        # fill in chunks to avoid a huge buffer
        hi = color >> 8
        lo = color & 0xFF
        chunk_px = 128
        line = bytearray(chunk_px * 2)
        for i in range(0, chunk_px * 2, 2):
            line[i] = hi
            line[i + 1] = lo
        self._set_window(0, 0, self.width - 1, self.height - 1)
        self.cs(0)
        self.dc(1)
        total = self.width * self.height
        left = total
        while left > 0:
            n = chunk_px if left >= chunk_px else left
            if n == chunk_px:
                self.spi.write(line)
            else:
                self.spi.write(memoryview(line)[: n * 2])
            left -= n
        self.cs(1)

    def pixel(self, x, y, color):
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        self._buf4[0] = color >> 8
        self._buf4[1] = color & 0xFF
        self._set_window(x, y, x, y)
        self.cs(0)
        self.dc(1)
        self.spi.write(memoryview(self._buf4)[:2])
        self.cs(1)
