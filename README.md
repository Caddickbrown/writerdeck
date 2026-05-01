# Writerdeck

Distraction-free writing UI for Raspberry Pi Zero 2W (HDMI output).

Built with [Textual](https://textual.textualize.io/) — a modern Python TUI framework.

## Setup

```bash
pip install textual
python3 scribe.py
```

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+N` | New document |
| `Ctrl+S` | Save (→ `~/Documents/scribe/log_YYYY-MM-DD_HHMM.txt`) |
| `Ctrl+O` | Open last saved log |
| `Ctrl+Q` | Quit |

## Auto-launch on boot

Add to `/etc/rc.local` before `exit 0`:

```bash
cd /home/pi/writerdeck
python3 scribe.py &
```

## Display

Designed for HDMI output. Works in any terminal — just `python3 scribe.py`.

## Roadmap

- [ ] Mode switching (Writing / Observation / Survival)
- [ ] E-ink display support (Waveshare 7.5")
- [ ] Battery status from Power Management HAT
- [ ] Git auto-commit on save
- [ ] Wi-Fi toggle
