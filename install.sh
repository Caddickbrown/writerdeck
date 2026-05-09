#!/usr/bin/env bash
# Scribe installer
# Usage: ./install.sh

set -e

INSTALL_DIR="$HOME/writerdeck"
DOCS_DIR="$HOME/Documents/scribe"
SERVICE_NAME="scribe"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'
BOLD='\033[1m'

ok()   { echo -e "${GREEN}✓${RESET} $1"; }
warn() { echo -e "${YELLOW}!${RESET} $1"; }
err()  { echo -e "${RED}✗${RESET} $1"; exit 1; }
step() { echo -e "\n${BOLD}$1${RESET}"; }

# ── Header ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Scribe — distraction-free writing for Pi Zero 2W${RESET}"
echo "──────────────────────────────────────────────────"
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────
step "Checking Python..."
if ! command -v python3 &>/dev/null; then
    err "Python 3 not found. Install with: sudo apt install python3 python3-pip"
fi
PY_VERSION=$(python3 --version 2>&1)
ok "$PY_VERSION found"

# ── Install Textual ───────────────────────────────────────────────────────────
step "Installing dependencies..."
if python3 -c "import textual" &>/dev/null; then
    TEXTUAL_VERSION=$(python3 -c "import textual; print(textual.__version__)" 2>/dev/null || echo "installed")
    ok "Textual already installed ($TEXTUAL_VERSION)"
else
    echo "Installing Textual..."
    pip3 install textual --quiet && ok "Textual installed" || err "Failed to install Textual. Try: pip3 install textual"
fi

# ── Optional hardware packages (Raspberry Pi only) ────────────────────────────
if command -v raspi-config &>/dev/null; then
    step "Optional hardware support (Raspberry Pi)"
    echo "  Install BME280 sensor support? (temp/humidity/pressure via I2C)"
    read -r -p "  [y/N] " bme_response
    if [[ "$bme_response" =~ ^[Yy]$ ]]; then
        pip3 install smbus2 RPi.bme280 --quiet && ok "BME280 support installed" || \
            warn "BME280 install failed — try: pip3 install smbus2 RPi.bme280"
        warn "Enable I2C: sudo raspi-config → Interface Options → I2C"
    fi

    echo ""
    echo "  Install GPS support? (requires gpsd running)"
    read -r -p "  [y/N] " gps_response
    if [[ "$gps_response" =~ ^[Yy]$ ]]; then
        sudo apt-get install -y gpsd gpsd-clients --quiet 2>/dev/null && \
            pip3 install gpsd-py3 --quiet && ok "GPS support installed" || \
            warn "GPS install failed — try: sudo apt install gpsd && pip3 install gpsd-py3"
    fi

    echo ""
    echo "  Install rfkill for Wi-Fi toggle (Ctrl+W)?"
    read -r -p "  [y/N] " rfkill_response
    if [[ "$rfkill_response" =~ ^[Yy]$ ]]; then
        sudo apt-get install -y rfkill --quiet 2>/dev/null && ok "rfkill installed" || \
            warn "rfkill install failed — try: sudo apt install rfkill"
    fi
fi

# ── Set up git repo for logs ──────────────────────────────────────────────────
step "Git log repository"
if command -v git &>/dev/null; then
    if [[ ! -d "$DOCS_DIR/.git" ]]; then
        git -C "$DOCS_DIR" init --quiet && ok "Initialised git repo in $DOCS_DIR"
        echo ".DS_Store" > "$DOCS_DIR/.gitignore"
        echo "Thumbs.db" >> "$DOCS_DIR/.gitignore"
    else
        ok "Git repo already exists in $DOCS_DIR"
    fi
    echo ""
    echo "  To sync logs to a remote, add one:"
    echo "    cd $DOCS_DIR && git remote add origin <url>"
    echo "  Then use Ctrl+G in Scribe to push."
else
    warn "git not found — auto-commit disabled. Install with: sudo apt install git"
fi

# ── Create directories ────────────────────────────────────────────────────────
step "Setting up directories..."
mkdir -p "$INSTALL_DIR"
ok "Install dir: $INSTALL_DIR"
mkdir -p "$DOCS_DIR"
ok "Logs dir:    $DOCS_DIR"

# ── Copy files ────────────────────────────────────────────────────────────────
step "Installing Scribe..."
cp scribe.py "$INSTALL_DIR/scribe.py"
chmod +x "$INSTALL_DIR/scribe.py"
ok "Copied scribe.py → $INSTALL_DIR/scribe.py"

# Create a launcher script in /usr/local/bin if writable
if [ -w /usr/local/bin ]; then
    cat > /usr/local/bin/scribe << EOF
#!/usr/bin/env bash
python3 $INSTALL_DIR/scribe.py "\$@"
EOF
    chmod +x /usr/local/bin/scribe
    ok "Launcher installed → run 'scribe' from anywhere"
else
    warn "Can't write to /usr/local/bin — run with: python3 ~/writerdeck/scribe.py"
    warn "Or: sudo ./install.sh to install the 'scribe' command system-wide"
fi

# ── Detect OS ─────────────────────────────────────────────────────────────────
OS="linux"
[[ "$(uname)" == "Darwin" ]] && OS="mac"

# ── Auto-launch on boot ───────────────────────────────────────────────────────
step "Auto-launch on boot (optional)"
if [[ "$OS" == "mac" ]]; then
    echo "  On Mac, this adds a launchd agent — Scribe opens in a new Terminal window at login."
else
    echo "  On Pi/Linux, this sets Scribe to launch automatically on the HDMI terminal at boot."
fi
echo ""
read -r -p "  Set up auto-launch? [y/N] " boot_response

if [[ "$boot_response" =~ ^[Yy]$ ]]; then

    if [[ "$OS" == "mac" ]]; then
        # ── macOS: launchd agent ──────────────────────────────────────────────
        LAUNCH_DIR="$HOME/Library/LaunchAgents"
        PLIST="$LAUNCH_DIR/com.scribe.writer.plist"
        mkdir -p "$LAUNCH_DIR"

        cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.scribe.writer</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>Terminal</string>
        <string>${INSTALL_DIR}/scribe.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/scribe.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/scribe.log</string>
</dict>
</plist>
EOF
        launchctl load "$PLIST" 2>/dev/null && \
            ok "launchd agent installed — Scribe will open at login" || \
            warn "Couldn't load agent — try: launchctl load $PLIST"

    elif command -v systemctl &>/dev/null && systemctl --version &>/dev/null 2>&1; then
        # ── Linux: systemd user service ───────────────────────────────────────
        SERVICE_DIR="$HOME/.config/systemd/user"
        mkdir -p "$SERVICE_DIR"

        cat > "$SERVICE_DIR/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Scribe — distraction-free writing
After=default.target

[Service]
Type=simple
ExecStart=python3 ${INSTALL_DIR}/scribe.py
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/tty1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

        systemctl --user daemon-reload
        systemctl --user enable "$SERVICE_NAME" 2>/dev/null && \
            ok "Systemd user service enabled (${SERVICE_NAME}.service)" || \
            warn "Couldn't enable service — try: systemctl --user enable scribe"

        echo ""
        echo -e "  ${YELLOW}Note:${RESET} For HDMI auto-launch, enable Console Autologin on the Pi:"
        echo "    sudo raspi-config → System Options → Boot / Auto Login → Console Autologin"

    else
        # ── Fallback: shell profile ───────────────────────────────────────────
        # Pick the right shell profile
        if [[ "$OS" == "mac" ]]; then
            PROFILE="$HOME/.zshrc"
        elif [ -f "$HOME/.bashrc" ]; then
            PROFILE="$HOME/.bashrc"
        else
            PROFILE="$HOME/.profile"
        fi

        MARKER="# Scribe auto-launch"
        if grep -q "$MARKER" "$PROFILE" 2>/dev/null; then
            warn "Auto-launch already in $PROFILE — skipping"
        else
            cat >> "$PROFILE" << 'SHELLEOF'

# Scribe auto-launch
if [[ -z "$DISPLAY" && "$(tty)" == "/dev/tty1" ]]; then
    python3 ~/writerdeck/scribe.py
fi
SHELLEOF
            ok "Added auto-launch to $PROFILE"
        fi
    fi

else
    warn "Skipping auto-launch — run manually with: scribe"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}──────────────────────────────────────────────────${RESET}"
echo -e "${GREEN}Done!${RESET}"
echo ""
echo "  Run now:    python3 ~/writerdeck/scribe.py"
if [ -x /usr/local/bin/scribe ]; then
    echo "  Or:         scribe"
fi
echo ""
echo "  Logs saved to: $DOCS_DIR"
echo ""
