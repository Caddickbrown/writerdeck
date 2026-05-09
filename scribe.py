#!/usr/bin/env python3
"""
Scribe — distraction-free writing UI for Pi Zero 2W
Requires: pip install textual
Optional: pip install smbus2 RPi.bme280 gpsd-py3
"""

import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static, TextArea

# ─── Optional hardware ────────────────────────────────────────────────────────

try:
    import smbus2
    import bme280 as _bme280
    _bme280_bus = smbus2.SMBus(1)
    _bme280_params = _bme280.load_calibration_params(_bme280_bus, 0x76)
    HAS_BME280 = True
except Exception:
    HAS_BME280 = False

try:
    import gpsd as _gpsd
    HAS_GPS = True
except ImportError:
    HAS_GPS = False


# ─── Modes ────────────────────────────────────────────────────────────────────

MODES = [
    ("✎", "Writing"),
    ("◎", "Observation"),
    ("⚡", "Survival"),
]

TEMPLATES = {
    "Writing": "",
    "Observation": (
        "OBSERVATION LOG — {date} {time}\n"
        "─────────────────────────────────\n"
        "Temp:     {temp}\n"
        "Humidity: {humidity}\n"
        "Pressure: {pressure}\n"
        "Location: {gps}\n"
        "Weather:  \n"
        "Mood:     \n"
        "\n"
        "Notes:\n\n"
    ),
    "Survival": (
        "SURVIVAL LOG — {date} {time}\n"
        "──────────────────────────────\n"
        "Battery: {battery}\n"
        "Temp:    {temp}\n"
        "\n"
        "Resources:\n"
        "  Water: \n"
        "  Food:  \n"
        "  Fuel:  \n"
        "\n"
        "Checklist:\n"
        "  [ ] \n"
        "  [ ] \n"
        "  [ ] \n"
        "\n"
        "Notes:\n\n"
    ),
}


# ─── System info ──────────────────────────────────────────────────────────────

def get_battery() -> str:
    """Read battery — macOS and Linux."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=2
            ).stdout
            import re
            m = re.search(r"(\d+)%", out)
            return m.group(1) + "%" if m else "--"
        except Exception:
            return "--"
    psu_dir = Path("/sys/class/power_supply")
    if psu_dir.exists():
        for psu in sorted(psu_dir.iterdir()):
            cap = psu / "capacity"
            psu_type = psu / "type"
            try:
                kind = psu_type.read_text().strip() if psu_type.exists() else ""
                if kind == "Battery" or "BAT" in psu.name.upper():
                    return cap.read_text().strip() + "%"
            except OSError:
                pass
    return "--"


def _get_macos_wifi_iface() -> str | None:
    """Return the macOS Wi-Fi interface name (e.g. en0)."""
    try:
        ports = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=3
        ).stdout
        lines = ports.splitlines()
        for i, line in enumerate(lines):
            if "wi-fi" in line.lower() or "airport" in line.lower():
                for j in range(i, min(i + 5, len(lines))):
                    if "Device:" in lines[j]:
                        return lines[j].split("Device:")[1].strip()
    except Exception:
        pass
    return None


def get_wifi() -> str:
    """Check WiFi state — macOS and Linux."""
    if sys.platform == "darwin":
        iface = _get_macos_wifi_iface()
        if iface:
            try:
                out = subprocess.run(
                    ["networksetup", "-getairportnetwork", iface],
                    capture_output=True, text=True, timeout=2
                ).stdout.lower()
                if out.strip() and "not associated" not in out and "error" not in out:
                    return "Wi-Fi: On"
                return "Wi-Fi: Off"
            except Exception:
                pass
        return "Wi-Fi: --"
    net_dir = Path("/sys/class/net")
    if net_dir.exists():
        for iface in sorted(net_dir.iterdir()):
            if iface.name.startswith(("wlan", "wlp", "wifi")):
                try:
                    state = (iface / "operstate").read_text().strip()
                    return "Wi-Fi: On" if state == "up" else "Wi-Fi: Off"
                except OSError:
                    pass
    return "Wi-Fi: --"


def toggle_wifi() -> str:
    """Toggle Wi-Fi on/off. Returns the new state string."""
    is_on = "On" in get_wifi()
    if sys.platform == "darwin":
        iface = _get_macos_wifi_iface()
        if iface:
            try:
                action = "off" if is_on else "on"
                subprocess.run(
                    ["networksetup", "-setairportpower", iface, action],
                    capture_output=True, timeout=5
                )
            except Exception:
                pass
    else:
        try:
            cmd = ["rfkill", "block", "wifi"] if is_on else ["rfkill", "unblock", "wifi"]
            subprocess.run(cmd, capture_output=True, timeout=5)
        except Exception:
            pass
    return "Wi-Fi: Off" if is_on else "Wi-Fi: On"


# ─── Hardware sensors ─────────────────────────────────────────────────────────

def get_bme280() -> dict | None:
    """Read BME280 temp/humidity/pressure. Returns None if unavailable."""
    if not HAS_BME280:
        return None
    try:
        data = _bme280.sample(_bme280_bus, 0x76, _bme280_params)
        return {
            "temp_c": round(data.temperature, 1),
            "temp_f": round(data.temperature * 9 / 5 + 32, 1),
            "humidity": round(data.humidity, 1),
            "pressure": round(data.pressure, 1),
        }
    except Exception:
        return None


def get_gps_coords(timeout: float = 2.0) -> dict | None:
    """Read GPS lat/lon via gpsd with a timeout. Returns None if unavailable."""
    if not HAS_GPS:
        return None
    result: dict = {}

    def _read() -> None:
        try:
            _gpsd.connect()
            packet = _gpsd.get_current()
            if packet.mode >= 2:
                result["lat"] = round(packet.lat, 4)
                result["lon"] = round(packet.lon, 4)
        except Exception:
            pass

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result or None


# ─── Git & sync ───────────────────────────────────────────────────────────────

def git_autocommit(path: Path, on_done) -> None:
    """Stage and commit a file in a background thread. Calls on_done(msg) on success."""
    def _run() -> None:
        docs = path.parent
        try:
            if not (docs / ".git").exists():
                subprocess.run(["git", "init"], cwd=docs, capture_output=True, timeout=10)
                gitignore = docs / ".gitignore"
                if not gitignore.exists():
                    gitignore.write_text(".DS_Store\nThumbs.db\n")
                subprocess.run(
                    ["git", "add", ".gitignore"],
                    cwd=docs, capture_output=True, timeout=5
                )
            subprocess.run(["git", "add", path.name], cwd=docs, capture_output=True, timeout=5)
            result = subprocess.run(
                ["git", "commit", "-m", f"log: {path.name}"],
                cwd=docs, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                on_done("✓ Committed")
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def git_push(docs_dir: Path, on_done) -> None:
    """Push all commits to remote in a background thread. Calls on_done(msg)."""
    def _run() -> None:
        try:
            result = subprocess.run(
                ["git", "push"],
                cwd=docs_dir, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                on_done("✓ Synced to remote")
            else:
                err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "push failed"
                on_done(f"Sync: {err[:50]}")
        except FileNotFoundError:
            on_done("git not installed")
        except Exception as e:
            on_done(f"Sync error: {str(e)[:40]}")

    threading.Thread(target=_run, daemon=True).start()


# ─── USB dump ─────────────────────────────────────────────────────────────────

def find_usb_drives() -> list[Path]:
    """Return paths of mounted USB drives."""
    if sys.platform == "darwin":
        skip = {"Macintosh HD", "Preboot", "Recovery", "VM", "Update"}
        volumes = Path("/Volumes")
        return [d for d in volumes.iterdir() if d.is_dir() and d.name not in skip] if volumes.exists() else []
    drives: list[Path] = []
    try:
        for line in Path("/proc/mounts").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                mp = Path(parts[1])
                if any(str(mp).startswith(p) for p in ("/media/", "/mnt/", "/run/media/")):
                    if mp.is_dir():
                        drives.append(mp)
    except Exception:
        pass
    return drives


def dump_logs_to_usb(docs_dir: Path, usb: Path) -> int:
    """Copy all .txt logs to <usb>/scribe_logs/. Returns count copied."""
    dest = usb / "scribe_logs"
    dest.mkdir(exist_ok=True)
    count = 0
    for f in docs_dir.glob("*.txt"):
        shutil.copy2(f, dest / f.name)
        count += 1
    return count


# ─── Search modal ─────────────────────────────────────────────────────────────

class SearchScreen(ModalScreen):
    """Full-screen log search."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    CSS = """
    SearchScreen {
        align: center middle;
    }

    #search-dialog {
        width: 80%;
        height: 70%;
        background: #1e1e1e;
        border: solid #444444;
        padding: 1 2;
    }

    #search-title {
        height: 1;
        color: #888888;
        margin-bottom: 1;
    }

    #search-input {
        margin-bottom: 1;
        border: solid #444444;
    }

    #search-input:focus {
        border: solid #6699cc;
    }

    #results-label {
        height: 1;
        color: #555555;
        margin-bottom: 1;
    }

    ListView {
        background: #1e1e1e;
        border: none;
    }

    ListItem {
        background: #1e1e1e;
        color: #aaaaaa;
        padding: 0 1;
    }

    ListItem.--highlight {
        background: #2a3a4a;
        color: #dddddd;
    }

    #no-results {
        color: #555555;
        padding: 1;
    }
    """

    def __init__(self, docs_dir: Path) -> None:
        super().__init__()
        self._docs = docs_dir
        self._files: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="search-dialog"):
            yield Static("Search logs  (↑↓ navigate, Enter open, Esc close)", id="search-title")
            yield Input(placeholder="Type to search...", id="search-input")
            yield Static("", id="results-label")
            yield ListView(id="results-list")

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        self._show_all()

    def _show_all(self) -> None:
        """Show all log files when search is empty."""
        lv = self.query_one(ListView)
        lv.clear()
        if not self._docs.exists():
            lv.append(ListItem(Label("No logs saved yet", id="no-results")))
            return
        self._files = sorted(self._docs.glob("*.txt"), reverse=True)
        label = self.query_one("#results-label", Static)
        label.update(f"{len(self._files)} log file(s)")
        for f in self._files[:30]:
            preview = f.read_text()[:60].replace("\n", " ")
            lv.append(ListItem(Label(f"  {f.name}  —  {preview}")))

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        lv = self.query_one(ListView)
        lv.clear()
        label = self.query_one("#results-label", Static)

        if not query:
            self._show_all()
            return

        if not self._docs.exists():
            label.update("No logs saved yet")
            return

        matches = []
        for f in sorted(self._docs.glob("*.txt"), reverse=True):
            try:
                content = f.read_text()
                if query in content.lower():
                    snippet = ""
                    for line in content.splitlines():
                        if query in line.lower():
                            snippet = line.strip()[:60]
                            break
                    matches.append((f, snippet))
            except OSError:
                pass

        self._files = [m[0] for m in matches]
        label.update(f"{len(matches)} match(es)")

        if not matches:
            lv.append(ListItem(Label("  No matches found")))
        else:
            for f, snippet in matches[:30]:
                lv.append(ListItem(Label(f"  {f.name}  —  {snippet}")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if self._files and idx is not None and idx < len(self._files):
            self.dismiss(self._files[idx])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        lv = self.query_one(ListView)
        if lv.index is None and self._files:
            self.dismiss(self._files[0])


# ─── Widgets ──────────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Top bar: mode, date, time, focus state, wifi, battery."""

    current_mode: reactive[str] = reactive("WRITING")

    def on_mount(self) -> None:
        self.set_interval(30, self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        now = datetime.now()
        date_str = now.strftime("%b %d, %Y")
        time_str = now.strftime("%H:%M")
        wifi = get_wifi()
        batt = get_battery()
        focus = "Connected" if "On" in wifi else "Focused"
        self.update(
            f"✎ {self.current_mode} MODE    "
            f"{date_str}  {time_str}    "
            f"{focus}    {wifi}    Batt: {batt}"
        )

    def watch_current_mode(self, _: str) -> None:
        self._refresh()


class ModeButton(Static):
    """A single clickable mode in the sidebar."""

    class Pressed(Message):
        def __init__(self, icon: str, label: str) -> None:
            super().__init__()
            self.icon = icon
            self.label = label

    def __init__(self, icon: str, label: str, active: bool = False) -> None:
        super().__init__()
        self._icon = icon
        self._label = label
        self._active = active

    def on_mount(self) -> None:
        self.update(f" {self._icon}  {self._label}\n    Mode")
        if self._active:
            self.add_class("active")

    def on_click(self) -> None:
        self.post_message(self.Pressed(self._icon, self._label))


class Sidebar(Vertical):
    """Left sidebar with mode list."""

    def compose(self) -> ComposeResult:
        for i, (icon, label) in enumerate(MODES):
            yield ModeButton(icon, label, active=(i == 0))


class BottomBar(Static):
    """Bottom toolbar with shortcuts."""

    def on_mount(self) -> None:
        self.update(
            "  ^N New    ^S Save    ^O Open    ^F Find    "
            "^G Sync    ^W Wi-Fi    ^U USB    ^1/2/3 Mode    ^Q Quit"
        )


# ─── App ──────────────────────────────────────────────────────────────────────

class ScribeApp(App):
    """The Scribe writing app."""

    TITLE = "Scribe"

    CSS = """
    Screen {
        background: #1a1a1a;
    }

    StatusBar {
        height: 1;
        background: #111111;
        color: #888888;
        content-align: left middle;
        padding: 0 2;
    }

    Sidebar {
        width: 20;
        background: #141414;
        border-right: solid #2a2a2a;
        padding: 1 0;
    }

    ModeButton {
        height: 4;
        padding: 1 1;
        color: #555555;
        margin: 0 0 1 0;
        border-left: solid #141414;
    }

    ModeButton.active {
        color: #dddddd;
        background: #1e1e1e;
        border-left: solid #6699cc;
    }

    ModeButton:hover {
        color: #aaaaaa;
        background: #1a1a1a;
    }

    TextArea {
        background: #1a1a1a;
        color: #cccccc;
        border: none;
        padding: 2 4;
    }

    TextArea > .text-area--cursor {
        background: #6699cc;
    }

    BottomBar {
        height: 1;
        background: #111111;
        color: #555555;
        content-align: left middle;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_doc", "New", show=False),
        Binding("ctrl+s", "save", "Save", show=False),
        Binding("ctrl+o", "open_last", "Open last", show=False),
        Binding("ctrl+f", "search", "Search", show=False, priority=True),
        Binding("ctrl+g", "git_sync", "Sync", show=False, priority=True),
        Binding("ctrl+w", "toggle_wifi", "Wi-Fi", show=False, priority=True),
        Binding("ctrl+u", "usb_dump", "USB dump", show=False, priority=True),
        Binding("ctrl+1", "mode_0", "Writing", show=False),
        Binding("ctrl+2", "mode_1", "Observation", show=False),
        Binding("ctrl+3", "mode_2", "Survival", show=False),
        Binding("ctrl+tab", "next_mode", "Next mode", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    _current_mode_idx: reactive[int] = reactive(0)

    @property
    def _docs(self) -> Path:
        return Path.home() / "Documents" / "scribe"

    def compose(self) -> ComposeResult:
        yield StatusBar(id="statusbar")
        with Horizontal():
            yield Sidebar(id="sidebar")
            yield TextArea(id="editor")
        yield BottomBar()

    def on_mount(self) -> None:
        self.query_one(TextArea).focus()

    # ── Mode switching ────────────────────────────────────────────────────────

    def _switch_to_mode(self, idx: int) -> None:
        idx = idx % len(MODES)
        self._current_mode_idx = idx
        icon, label = MODES[idx]
        for btn in self.query(ModeButton):
            btn.remove_class("active")
            if btn._label == label:
                btn.add_class("active")
        bar = self.query_one("#statusbar", StatusBar)
        bar.current_mode = label.upper()

    def on_mode_button_pressed(self, event: ModeButton.Pressed) -> None:
        for i, (icon, label) in enumerate(MODES):
            if label == event.label:
                self._switch_to_mode(i)
                break
        self.query_one(TextArea).focus()

    def action_mode_0(self) -> None:
        self._switch_to_mode(0)

    def action_mode_1(self) -> None:
        self._switch_to_mode(1)

    def action_mode_2(self) -> None:
        self._switch_to_mode(2)

    def action_next_mode(self) -> None:
        self._switch_to_mode(self._current_mode_idx + 1)

    # ── Document actions ──────────────────────────────────────────────────────

    def action_new_doc(self) -> None:
        _, mode_label = MODES[self._current_mode_idx]
        template = TEMPLATES.get(mode_label, "")
        now = datetime.now()

        # Read sensors synchronously (BME280 is fast; GPS has a short timeout)
        bme = get_bme280() if mode_label in ("Observation", "Survival") else None
        gps = get_gps_coords() if mode_label == "Observation" else None

        text = template.format(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            battery=get_battery(),
            temp=f"{bme['temp_f']}°F / {bme['temp_c']}°C" if bme else "",
            humidity=f"{bme['humidity']}%" if bme else "",
            pressure=f"{bme['pressure']} hPa" if bme else "",
            gps=f"{gps['lat']}, {gps['lon']}" if gps else "",
        )
        editor = self.query_one(TextArea)
        editor.load_text(text)
        editor.move_cursor_relative(rows=999)
        self.notify(f"New {mode_label} log")
        editor.focus()

    def action_save(self) -> None:
        editor = self.query_one(TextArea)
        text = editor.text
        if not text.strip():
            self.notify("Nothing to save", severity="warning")
            return
        _, mode_label = MODES[self._current_mode_idx]
        self._docs.mkdir(parents=True, exist_ok=True)
        prefix = mode_label.lower()
        filename = datetime.now().strftime(f"{prefix}_%Y-%m-%d_%H%M.txt")
        filepath = self._docs / filename
        filepath.write_text(text)
        self.notify(f"Saved → {filename}")
        git_autocommit(filepath, lambda msg: self.call_from_thread(self.notify, msg))

    def action_open_last(self) -> None:
        if not self._docs.exists():
            self.notify("No saved logs found", severity="warning")
            return
        _, mode_label = MODES[self._current_mode_idx]
        prefix = mode_label.lower()
        mode_files = sorted(self._docs.glob(f"{prefix}_*.txt"), reverse=True)
        all_files = sorted(self._docs.glob("*.txt"), reverse=True)
        files = mode_files or all_files
        if not files:
            self.notify("No saved logs found", severity="warning")
            return
        if not mode_files and all_files:
            self.notify(f"No {mode_label} logs — opening most recent", severity="information")
        self._load_file(files[0])

    def action_search(self) -> None:
        def on_result(path: Path | None) -> None:
            if path:
                self._load_file(path)

        self.push_screen(SearchScreen(self._docs), on_result)

    def _load_file(self, path: Path) -> None:
        editor = self.query_one(TextArea)
        editor.load_text(path.read_text())
        self.notify(f"Opened {path.name}")
        editor.focus()

    # ── Connectivity actions ──────────────────────────────────────────────────

    def action_toggle_wifi(self) -> None:
        new_state = toggle_wifi()
        self.query_one("#statusbar", StatusBar)._refresh()
        self.notify(new_state)

    def action_git_sync(self) -> None:
        if not self._docs.exists():
            self.notify("No logs directory — save something first", severity="warning")
            return
        self.notify("Syncing…")
        git_push(self._docs, lambda msg: self.call_from_thread(self.notify, msg))

    def action_usb_dump(self) -> None:
        drives = find_usb_drives()
        if not drives:
            self.notify("No USB drive detected", severity="warning")
            return
        if not self._docs.exists():
            self.notify("No logs to copy", severity="warning")
            return
        usb = drives[0]
        try:
            count = dump_logs_to_usb(self._docs, usb)
            self.notify(f"Copied {count} log(s) → {usb.name}/scribe_logs/")
        except Exception as e:
            self.notify(f"USB copy failed: {e}", severity="error")


if __name__ == "__main__":
    ScribeApp().run()
