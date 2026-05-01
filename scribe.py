#!/usr/bin/env python3
"""
Scribe — distraction-free writing UI for Pi Zero 2W
Requires: pip install textual
"""

from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static, TextArea


# ─── Modes ────────────────────────────────────────────────────────────────────

MODES = [
    ("✎", "Writing"),
    ("◎", "Observation"),
    ("⚡", "Survival"),
]


# ─── Widgets ──────────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Top bar: mode, date, time, battery."""

    current_mode: reactive[str] = reactive("WRITING")

    def on_mount(self) -> None:
        self.set_interval(30, self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        now = datetime.now()
        date_str = now.strftime("%b %d, %Y")
        time_str = now.strftime("%H:%M")
        batt = self._battery()
        self.update(
            f"✎ {self.current_mode} MODE    "
            f"{date_str}    {time_str}    "
            f"Focused    Wi-Fi: Off    Batt: {batt}"
        )

    def _battery(self) -> str:
        for path in [
            "/sys/class/power_supply/BAT0/capacity",
            "/sys/class/power_supply/BAT1/capacity",
        ]:
            try:
                return Path(path).read_text().strip() + "%"
            except OSError:
                pass
        return "--"

    def watch_current_mode(self, mode: str) -> None:
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
        self.update("  ^N New    ^O Open    ^S Save    ^Q Quit")


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
        Binding("ctrl+o", "open_last", "Open", show=False),
        Binding("ctrl+q", "quit", "Quit", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield StatusBar(id="statusbar")
        with Horizontal():
            yield Sidebar(id="sidebar")
            yield TextArea(id="editor")
        yield BottomBar()

    def on_mount(self) -> None:
        self.query_one(TextArea).focus()

    def on_mode_button_pressed(self, event: ModeButton.Pressed) -> None:
        # Update sidebar active state
        for btn in self.query(ModeButton):
            btn.remove_class("active")
            if btn._label == event.label:
                btn.add_class("active")
        # Update status bar
        bar = self.query_one("#statusbar", StatusBar)
        bar.current_mode = event.label.upper()

    def action_new_doc(self) -> None:
        editor = self.query_one(TextArea)
        editor.load_text("")
        self.notify("New document")

    def action_save(self) -> None:
        editor = self.query_one(TextArea)
        text = editor.text
        if not text.strip():
            self.notify("Nothing to save", severity="warning")
            return
        docs = Path.home() / "Documents" / "scribe"
        docs.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("log_%Y-%m-%d_%H%M.txt")
        (docs / filename).write_text(text)
        self.notify(f"Saved → {filename}")

    def action_open_last(self) -> None:
        docs = Path.home() / "Documents" / "scribe"
        files = sorted(docs.glob("*.txt")) if docs.exists() else []
        if not files:
            self.notify("No saved logs found", severity="warning")
            return
        latest = files[-1]
        editor = self.query_one(TextArea)
        editor.load_text(latest.read_text())
        self.notify(f"Opened {latest.name}")


if __name__ == "__main__":
    ScribeApp().run()
