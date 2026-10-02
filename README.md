# W55MH32 Album Player


Plays **16-bit stereo 44.1 kHz WAV** (smooth on this board). MP3 is converted on the PC.

## 1. Name your media

Each song and photo must share the same basename:

```text
music/海闊天空.mp3
photo/海闊天空.png
```

## 2. Install PC tools

```powershell
python -m pip install pillow
winget install ffmpeg
```

## 3A. Full SD package (recommended)

```powershell
python prepare_media.py --music music --photo photo --output prepared_sd --volume 50
```

Copy `prepared_sd` contents to the SD card root:

```text
/playlist.json
/music/000.wav
/music/001.wav
/ui/000.rgb565
/ui/001.rgb565
```

## 3B. Convert songs only

```powershell
python convert_to_wav.py --input music --output wav_out --ascii-names
```

Then copy `000.wav`, `001.wav`, … to `/music` on the SD card.

## 4. Board files

```text
main.py
audio_player.py
photo_display.py
st7789_min.py
time_bar.py         
playback_overlay.py  
```

## Controls

- `PF13`: next song (`pressed == 0`, pull-up)
- `PF11`: pause / resume
- Playlist wraps after the last track

WAV playback uses a large I2S buffer (`ibuf` up to 20000), same idea as the board WAV test.

