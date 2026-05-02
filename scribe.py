#!/usr/bin/env python3
"""
Scribe — distraction-free writing UI for Pi Zero 2W
Requires: pip install textual
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static, TextArea


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
        "Weather: \n"
        "Temp: \n"
        "Mood: \n"
        "Location: \n"
        "\n"
        "Notes:\n\n"
    ),
    "Survival": (
        "SURVIVAL LOG — {date} {time}\n"
        "──────────────────────────────\n"
        "Battery: {battery}\n"
        "\n"
        "Resources:\n"
        "  Water: \n"
        "  Food: \n"
        "  Fuel: \n"
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
    # Linux: scan /sys/class/power_supply/
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


def get_wifi() -> str:
    """Check WiFi state — macOS and Linux."""
    if sys.platform == "darwin":
        try:
            # Discover the actual WiFi interface name from hardware ports
            ports = subprocess.run(
                ["networksetup", "-listallhardwareports"],
                capture_output=True, text=True, timeout=3
            ).stdout
            wifi_iface = None
            lines = ports.splitlines()
            for i, line in enumerate(lines):
                if "wi-fi" in line.lower() or "airport" in line.lower():
                    for j in range(i, min(i + 5, len(lines))):
                        if "Device:" in lines[j]:
                            wifi_iface = lines[j].split("Device:")[1].strip()
                            break
                    break
            if wifi_iface:
                out = subprocess.run(
                    ["networksetup", "-getairportnetwork", wifi_iface],
                    capture_output=True, text=True, timeout=2
                ).stdout.lower()
                if "current wi-fi network" in out:
                    return "Wi-Fi: On"
                return "Wi-Fi: Off"
        except Exception:
            pass
        return "Wi-Fi: --"
    # Linux: check /sys/class/net/
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
                    # Find the first matching line for preview
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
    """Top bar: mode, date, time, wifi, battery."""

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
        self.update(
            f"✎ {self.current_mode} MODE    "
            f"{date_str}  {time_str}    "
            f"Focused    {wifi}    Batt: {batt}"
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
            "  ^N New    ^S Save    ^O Open last    ^F Search    "
            "^1/2/3 Mode    ^Tab Cycle    ^Q Quit"
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
        Binding("ctrl+f", "search", "Search", show=False),
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
        text = template.format(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            battery=get_battery(),
        )
        editor = self.query_one(TextArea)
        editor.load_text(text)
        # Move cursor to end
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
        (self._docs / filename).write_text(text)
        self.notify(f"Saved → {filename}")

    def action_open_last(self) -> None:
        files = sorted(self._docs.glob("*.txt"), reverse=True) if self._docs.exists() else []
        if not files:
            self.notify("No saved logs found", severity="warning")
            return
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


if __name__ == "__main__":
    ScribeApp().run()
