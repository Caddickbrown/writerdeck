# Writerdeck — Build Guide

A step-by-step guide for building the Off-Grid Digital Scribe from scratch.

---

## Table of Contents

1. [Overview](#overview)
2. [Bill of Materials](#bill-of-materials)
3. [Tools](#tools)
4. [Phase 1 — OS Setup](#phase-1--os-setup)
5. [Phase 2 — Hardware Wiring](#phase-2--hardware-wiring)
6. [Phase 3 — Software Installation](#phase-3--software-installation)
7. [Phase 4 — Sensors & GPS](#phase-4--sensors--gps)
8. [Phase 5 — Sync & Backup](#phase-5--sync--backup)
9. [Phase 6 — Power & Solar](#phase-6--power--solar)
10. [Phase 7 — Enclosure](#phase-7--enclosure)
11. [Troubleshooting](#troubleshooting)

---

## Overview

The Writerdeck is a minimal, off-grid writing device built around a Raspberry Pi Zero 2W. It logs everything to plain `.txt` files, auto-commits to git, and syncs when Wi-Fi is available. It runs entirely in a terminal — no desktop environment needed.

**Data flow:**
```
Write → Save (TXT) → Git auto-commit → Wi-Fi push → Remote / Syncthing
                   → Ctrl+U dump   → USB drive
```

**Three modes:**
- **Writing** — freeform journaling and notes
- **Observation** — structured template with live temp, humidity, pressure, GPS
- **Survival** — battery, temperature, resource tracking, checklist

---

## Bill of Materials

### Core

| Part | Notes | Est. cost |
|------|-------|-----------|
| Raspberry Pi Zero 2W | With header pre-soldered if possible | ~$15 |
| microSD card, 32GB+ | Class 10 / A1 rated | ~$10 |
| USB-C breakout / power input | For charging port on enclosure | ~$3 |
| Micro-USB OTG adapter | To connect the keyboard USB | ~$3 |
| USB hub (micro-USB) | If you need USB + charging simultaneously | ~$8 |

### Display

The software currently runs as a terminal UI over HDMI. Two display paths:

**Option A — HDMI display (simplest, current)**

| Part | Notes | Est. cost |
|------|-------|-----------|
| 7.5" IPS HDMI display | 800×480, look for "Raspberry Pi display" | ~$35–50 |
| Mini-HDMI to HDMI adapter / cable | Pi Zero uses mini-HDMI | ~$5 |

**Option B — Waveshare 7.5" E-Ink (intended, low power)**

| Part | Notes | Est. cost |
|------|-------|-----------|
| Waveshare 7.5" e-Paper HAT (V2) | 800×480, SPI, SKU 13187 | ~$55–65 |

> E-ink display support (framebuffer rendering of the Textual UI) is on the roadmap. For now, use Option A and swap later.

### Input

| Part | Notes | Est. cost |
|------|-------|-----------|
| 60% QMK mechanical keyboard | Any USB 60% with QMK firmware | ~$40–80 |
| Keyswitches + keycaps | Choose your switches; DSA blanks look clean | ~$20–40 |

### Sensors

| Part | Notes | Est. cost |
|------|-------|-----------|
| BME280 breakout | I2C, Adafruit #2652 or equivalent | ~$8–12 |
| u-blox NEO-6M GPS module | UART, includes ceramic antenna | ~$10–15 |
| DS3231 RTC module | I2C real-time clock with battery backup | ~$5 |

> Skip the DS3231 if using a PiJuice HAT — it has its own RTC.

### Power

| Part | Notes | Est. cost |
|------|-------|-----------|
| PiJuice HAT | Power management + RTC + I2C battery stats | ~$35–50 |
| 2600mAh Li-ion cell | 18650 format, fits PiJuice | ~$8–12 |
| 5V / 5W solar panel | For trickle charging via PiJuice | ~$15–20 |

> Alternatively: any USB-C Li-ion charging board + 3.7V cell + 5V boost converter. PiJuice is the easiest all-in-one.

### Enclosure

| Part | Notes | Est. cost |
|------|-------|-----------|
| 3D printed shell | See Enclosure section below | Material cost only |
| M2 / M2.5 standoffs + screws | For mounting the Pi | ~$5 |
| Small hinge (laptop-style) | 10–15mm barrel hinge works well | ~$5–10 |

**Estimated total: $220–$360** depending on display and enclosure choices.

---

## Tools

- Soldering iron + solder (for GPIO headers if not pre-soldered, and breakout boards)
- Multimeter
- Small Phillips and flathead screwdrivers
- Flush cutters
- 22–24 AWG hookup wire, jumper wires for prototyping
- Heat shrink tubing
- Computer with SD card reader (for flashing)

---

## Phase 1 — OS Setup

### 1.1 Flash Raspberry Pi OS Lite

Download **Raspberry Pi OS Lite (64-bit)** from raspberrypi.com.

Use Raspberry Pi Imager. Before writing:

- Click the gear icon (Advanced Options)
- Set hostname: `scribe`
- Enable SSH
- Set username/password (e.g. `pi` / your password)
- Configure Wi-Fi (for initial setup; you can disable it later)

Write to the microSD card.

### 1.2 First boot

Insert the card, connect HDMI and keyboard, power on. Wait for the login prompt.

```bash
# Update the system first
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip rfkill
```

### 1.3 Enable interfaces

```bash
sudo raspi-config
```

Navigate to **Interface Options** and enable:

- **I2C** — for BME280 and RTC
- **Serial Port** — for GPS (disable the serial *login shell*, keep the *hardware serial port*)
- **SPI** — only needed if using the Waveshare e-ink display

Reboot when prompted:

```bash
sudo reboot
```

### 1.4 Console autologin (for boot-to-Scribe)

```bash
sudo raspi-config
# → System Options → Boot / Auto Login → Console Autologin
```

This lets Scribe launch on `/dev/tty1` at power-on without a keyboard login.

---

## Phase 2 — Hardware Wiring

All sensors connect to the 40-pin GPIO header. Work from the Pi outward — connect sensors before powering on.

### Pi Zero 2W pinout reference (relevant pins)

```
 3.3V  [ 1][ 2]  5V
  SDA  [ 3][ 4]  5V
  SCL  [ 5][ 6]  GND
       [ 7][ 8]  TX (UART)
  GND  [ 9][10]  RX (UART)
       [11][12]
       [13][14]  GND
       [15][16]
 3.3V  [17][18]  GPIO24 (e-ink BUSY)
 MOSI  [19][20]  GND
 MISO  [21][22]  GPIO25 (e-ink DC)
 SCLK  [23][24]  CE0 (e-ink CS)
  GND  [25][26]
       [...]
```

### 2.1 BME280 (temperature, humidity, pressure) — I2C

| BME280 pin | Pi pin | Pi function |
|------------|--------|-------------|
| VIN / VCC | 1 | 3.3V |
| GND | 6 | GND |
| SDA | 3 | GPIO 2 (I2C SDA) |
| SCL | 5 | GPIO 3 (I2C SCL) |

> Make sure the module's I2C address is **0x76**. Some modules default to 0x77 — if so, pull the SDO pin low (connect SDO → GND).

### 2.2 DS3231 RTC — I2C

Shares the same I2C bus as the BME280. Only add the RTC if you are **not** using PiJuice (which has its own RTC at the same address).

| DS3231 pin | Pi pin | Pi function |
|------------|--------|-------------|
| VCC | 1 | 3.3V |
| GND | 6 | GND |
| SDA | 3 | GPIO 2 (shared) |
| SCL | 5 | GPIO 3 (shared) |

### 2.3 u-blox NEO-6M GPS — UART

The GPS transmits NMEA sentences over serial. Pi TX → GPS RX, Pi RX → GPS TX.

| GPS pin | Pi pin | Pi function |
|---------|--------|-------------|
| VCC | 2 | 5V (module has 3.3V regulator) |
| GND | 9 | GND |
| TX | 10 | GPIO 15 (UART RX) |
| RX | 8 | GPIO 14 (UART TX) |

> Connect the GPS antenna to the u.FL connector before testing. A small patch antenna is fine for outdoors use.

### 2.4 PiJuice HAT — stacked

The PiJuice stacks directly onto the full 40-pin header. Seat it firmly. Insert the 18650 cell into the holder (mind the polarity markings). The solar panel connects to the two-pin JST connector on the HAT.

After stacking, verify I2C addresses don't conflict:

```bash
sudo apt install -y i2c-tools
i2cdetect -y 1
```

Expected addresses:
- `0x14` — PiJuice fuel gauge / power management
- `0x20` — PiJuice IO (varies by firmware)
- `0x68` — PiJuice RTC (or DS3231 if not using PiJuice)
- `0x76` — BME280

### 2.5 Waveshare 7.5" E-Ink — SPI (Option B only)

Connect with ribbon cable to the HAT adapter, or wire directly:

| E-ink pin | Pi pin | Pi function |
|-----------|--------|-------------|
| VCC | 17 | 3.3V |
| GND | 20 | GND |
| DIN | 19 | GPIO 10 (SPI MOSI) |
| CLK | 23 | GPIO 11 (SPI SCLK) |
| CS | 24 | GPIO 8 (SPI CE0) |
| DC | 22 | GPIO 25 |
| RST | 11 | GPIO 17 |
| BUSY | 18 | GPIO 24 |

### 2.6 Keyboard — USB

The Pi Zero 2W has a single micro-USB OTG port (the inner port; the outer is power-only). Connect the keyboard via a micro-USB OTG adapter. If you need a USB hub for additional devices, chain it between the OTG adapter and the keyboard.

---

## Phase 3 — Software Installation

### 3.1 Clone the repository

```bash
cd ~
git clone https://github.com/Caddickbrown/writerdeck.git
cd writerdeck
```

### 3.2 Run the installer

```bash
chmod +x install.sh
./install.sh
```

The installer will:
- Install Textual (the TUI framework)
- Prompt for optional hardware packages (BME280, GPS, rfkill)
- Initialise a git repo in `~/Documents/scribe/` for auto-commits
- Optionally set up a systemd service to launch Scribe at boot on `/dev/tty1`

### 3.3 Verify the install

```bash
scribe
```

You should see the Scribe writing interface. Press `Ctrl+Q` to exit.

---

## Phase 4 — Sensors & GPS

### 4.1 BME280

Verify the sensor is detected:

```bash
i2cdetect -y 1
# Should show 0x76 in the grid
```

Install the Python library if the installer didn't:

```bash
pip3 install smbus2 RPi.bme280
```

Test it:

```python
python3 -c "
import smbus2, bme280
bus = smbus2.SMBus(1)
params = bme280.load_calibration_params(bus, 0x76)
data = bme280.sample(bus, 0x76, params)
print(f'Temp: {data.temperature:.1f}C  Hum: {data.humidity:.1f}%  Pressure: {data.pressure:.1f}hPa')
"
```

Now when you press `Ctrl+N` in Observation or Survival mode, these values fill in automatically.

### 4.2 DS3231 RTC

Load the RTC kernel module:

```bash
sudo modprobe rtc-ds3231
sudo bash -c 'echo ds3231 0x68 > /sys/class/i2c-adapter/i2c-1/new_device'
```

Read the hardware clock:

```bash
sudo hwclock -r
```

If the time is wrong, sync from the system clock (while internet is available):

```bash
sudo hwclock -w
```

To load the driver automatically at boot, add to `/etc/modules`:

```
i2c-bcm2835
rtc-ds3231
```

And add to `/etc/rc.local` (before `exit 0`):

```bash
echo ds3231 0x68 > /sys/class/i2c-adapter/i2c-1/new_device
hwclock -s
```

### 4.3 GPS (u-blox NEO-6M)

Disable the serial console so gpsd can use the UART:

```bash
sudo raspi-config
# → Interface Options → Serial Port
# → "Would you like a login shell over serial?" → No
# → "Would you like the serial port hardware to be enabled?" → Yes
```

Install gpsd:

```bash
sudo apt install -y gpsd gpsd-clients
pip3 install gpsd-py3
```

Configure gpsd to use the Pi's UART:

```bash
sudo nano /etc/default/gpsd
```

Set:

```
DEVICES="/dev/ttyAMA0"
GPSD_OPTIONS="-n"
START_DAEMON="true"
```

Start and enable:

```bash
sudo systemctl enable gpsd
sudo systemctl start gpsd
```

Test:

```bash
cgps -s
# Should show satellite data and eventually a fix (takes 1–3 min outdoors)
```

Once gpsd has a fix, `Ctrl+N` in Observation mode will auto-fill the GPS coordinates.

### 4.4 PiJuice battery status

Install the PiJuice software:

```bash
sudo apt install -y pijuice-base
pip3 install pijuice
```

Test:

```python
python3 -c "
from pijuice import PiJuice
pj = PiJuice(1, 0x14)
print(pj.status.GetChargeLevel())
print(pj.status.GetBatteryTemperature())
"
```

> The Scribe app currently reads battery via `/sys/class/power_supply/` (which PiJuice populates). Full PiJuice HAT integration — including temperature and charging state — is on the roadmap.

---

## Phase 5 — Sync & Backup

### 5.1 Git remote sync (Ctrl+G)

Create a private repository on GitHub, Gitea, or any git host. Then:

```bash
cd ~/Documents/scribe
git remote add origin git@github.com:yourname/scribe-logs.git
```

For SSH auth without a password prompt, add the Pi's public key to your git host:

```bash
ssh-keygen -t ed25519 -C "scribe"
cat ~/.ssh/id_ed25519.pub
# Paste this into GitHub → Settings → SSH Keys
```

Now `Ctrl+G` in Scribe will push all committed logs to the remote.

### 5.2 Syncthing (passive local sync)

Syncthing syncs `~/Documents/scribe/` to any device on the same network automatically — no cloud needed.

```bash
sudo apt install -y syncthing
sudo systemctl enable syncthing@pi
sudo systemctl start syncthing@pi
```

Access the Syncthing web UI from another machine (temporarily enable SSH tunnelling):

```bash
ssh -L 8384:localhost:8384 pi@scribe.local
# Then open http://localhost:8384 in your browser
```

Add a remote device (your laptop or phone), then share the `~/Documents/scribe/` folder with it.

After setup, Syncthing runs silently in the background whenever Wi-Fi is on. No action needed in Scribe.

### 5.3 USB data dump (Ctrl+U)

Plug in any USB drive. Scribe detects drives mounted under `/media/`, `/mnt/`, or `/run/media/`. Press `Ctrl+U` and all logs are copied to `<drive>/scribe_logs/`.

For auto-mounting USB drives on Pi OS:

```bash
sudo apt install -y usbmount
```

---

## Phase 6 — Power & Solar

### 6.1 PiJuice configuration

The PiJuice HAT manages charging automatically. Connect your solar panel to the two-pin JST connector. The panel charges the battery when light is available; the battery powers the Pi when solar is insufficient.

Check charging status:

```python
python3 -c "
from pijuice import PiJuice
pj = PiJuice(1, 0x14)
print('Charge:', pj.status.GetChargeLevel(), '%')
print('Status:', pj.status.GetStatus())
"
```

Configure wake-on-power-restore (so the Pi boots when solar power returns after a shutdown):

```bash
# In PiJuice CLI or web interface:
# Power Management → Wakeup On Charge → 0% (any charge level)
```

### 6.2 Expected battery life

| State | Current draw | Battery life (2600mAh) |
|-------|-------------|------------------------|
| Writing, Wi-Fi off | ~90–120mA | ~20–28 hours |
| Writing, Wi-Fi on | ~150–200mA | ~13–17 hours |
| Writing, e-ink display | ~80–100mA | ~26–32 hours |

A 5W solar panel produces ~1000mA in full sun. Even partial sun will sustain indefinite operation.

### 6.3 Safe shutdown

Add a hardware shutdown button (optional but recommended):

```bash
sudo nano /etc/rc.local
```

Add before `exit 0`:

```bash
python3 /home/pi/writerdeck/shutdown_button.py &
```

A simple script that watches a GPIO pin for a long press and calls `sudo shutdown -h now`. Connect a button between GPIO 26 and GND.

---

## Phase 7 — Enclosure

The reference design is a clamshell form factor: keyboard base + display lid, ~8mm profile, ~365g.

### 7.1 Design constraints

- Pi Zero 2W: 65mm × 30mm × 5mm
- PiJuice HAT stacks: adds ~10mm height
- 18650 cell: 65mm × 18mm diameter
- 7.5" display: 170mm × 111mm active area
- 60% keyboard PCB: ~285mm × 95mm

### 7.2 3D printing

A community-contributed enclosure design (Fusion 360 / STL) is the intended path. Until a design is published, here are the key considerations:

- **Keyboard base**: recess for the PCB + plate, space below for the Pi + HAT + battery
- **Display lid**: tight bezel around the screen, enough depth for the ribbon cable
- **Hinge**: 10–12mm barrel hinge, brass or stainless. Two per edge for rigidity
- **Ports exposed**: USB-C (power in), micro-USB OTG (keyboard in), mini-HDMI (optional), micro-SD slot access
- **Antenna**: leave a window or use a non-metallic section of the lid for GPS signal

Material: **PETG** is recommended over PLA for durability and slight flex at the hinge mount points.

### 7.3 Physical controls

The image specifies three dedicated hardware controls:

| Control | Function | Implementation |
|---------|----------|----------------|
| Mode switch | Cycle Writing → Observation → Survival | Rotary encoder or 3-pos toggle on GPIO |
| Wi-Fi toggle | Hard-disconnect Wi-Fi (rfkill) | SPDT switch on GPIO, script reads state |
| Custom button | User-defined (e.g. quick-save, shutdown) | Momentary button on GPIO |

For the Wi-Fi toggle switch, wire a SPDT to a GPIO pin and run a small daemon:

```python
# wifi_switch.py — run at boot via rc.local
import RPi.GPIO as GPIO, subprocess, time

SWITCH_PIN = 21  # adjust to your wiring

GPIO.setmode(GPIO.BCM)
GPIO.setup(SWITCH_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

while True:
    if GPIO.input(SWITCH_PIN) == GPIO.LOW:
        subprocess.run(["rfkill", "block", "wifi"])
    else:
        subprocess.run(["rfkill", "unblock", "wifi"])
    time.sleep(1)
```

---

## Troubleshooting

### Scribe doesn't launch at boot

Check the systemd service:

```bash
systemctl --user status scribe
journalctl --user -u scribe -n 50
```

If the service fails because the terminal isn't ready, add a short delay:

```bash
# In ~/.config/systemd/user/scribe.service, under [Service]:
ExecStartPre=/bin/sleep 3
```

### BME280 not detected (`i2cdetect` shows nothing)

- Confirm I2C is enabled: `sudo raspi-config → Interface Options → I2C`
- Check wiring — SDA to Pin 3, SCL to Pin 5, power and ground
- Try address 0x77 if 0x76 fails: some modules ship with SDO pulled high

### GPS has no fix

- The NEO-6M needs a clear sky view — test outdoors
- Cold start can take 1–3 minutes. Warm start (after a recent fix) is 15–30 seconds
- Confirm gpsd is running: `sudo systemctl status gpsd`
- Confirm the UART device: `ls /dev/ttyAMA*` — should show `/dev/ttyAMA0`
- Test raw NMEA output: `cat /dev/ttyAMA0` — you should see `$GPRMC` sentences

### Keyboard not recognised

- Check the OTG port (inner micro-USB), not the power port (outer)
- Try a powered USB hub if the keyboard draws too much current
- Confirm USB OTG mode: `lsusb` should list the keyboard after plugging in

### Git push fails (Ctrl+G)

- Confirm a remote is configured: `cd ~/Documents/scribe && git remote -v`
- Test SSH auth: `ssh -T git@github.com`
- If using HTTPS, store credentials: `git config credential.helper store`

### Battery percentage shows `--`

- PiJuice populates `/sys/class/power_supply/` — confirm with `ls /sys/class/power_supply/`
- Check PiJuice service: `sudo systemctl status pijuice`
- Test directly: `python3 -c "from pijuice import PiJuice; print(PiJuice(1,0x14).status.GetChargeLevel())"`

---

## Quick Reference

```
~/writerdeck/          Source code
~/Documents/scribe/    All log files (git repo)
/usr/local/bin/scribe  System-wide launcher

Ctrl+N   New log (sensor data auto-filled)
Ctrl+S   Save + git commit
Ctrl+O   Open last log
Ctrl+F   Full-text search
Ctrl+G   Git push to remote
Ctrl+W   Toggle Wi-Fi
Ctrl+U   Copy logs to USB
Ctrl+1   Writing mode
Ctrl+2   Observation mode
Ctrl+3   Survival mode
Ctrl+Q   Quit
```
