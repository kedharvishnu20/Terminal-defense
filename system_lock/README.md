# 🔒 System Lock Guard v2.0

A **cross-platform** multi-module blocker that controls keyboard, mouse, WiFi, Bluetooth, and USB access during configured time windows. No popups, no dialogs — modules silently activate and deactivate based on schedule and session events.

## ✨ Features

| Feature | Description |
|---------|-------------|
| ⌨ **Keyboard Blocking** | Suppresses all key presses via pynput |
| 🖱 **Mouse Blocking** | Suppresses all mouse movement and clicks |
| 📶 **WiFi Control** | Disables/enables WiFi adapter (needs admin) |
| 🔵 **Bluetooth Control** | Disables/enables Bluetooth radio (needs admin) |
| 🔌 **USB Storage Blocking** | Blocks USB mass storage devices (needs admin) |
| 🕐 **Time-based Scheduling** | Configure a time window for automatic activation |
| 🔓 **Session-aware** | Detects system lock/unlock events automatically |
| 🔑 **Secret Bypass** | ESC × N → type password → Enter to unlock all |
| 🖥️ **Cross-platform** | Works on Windows, macOS, and Linux |

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** installed and on PATH
- **Administrator/sudo** for WiFi, Bluetooth, and USB control

### Installation

```bash
pip install -r requirements.txt
```

### Running

**From project root (recommended):**
```batch
start.bat     →   Option [4] normal mode
              →   Option [5] test mode
              →   Option [6] view status
```

**Direct:**
```bash
python lock_guard.py             # Normal mode — waits for time window
python lock_guard.py --test      # Test mode — blocks everything immediately
python lock_guard.py --status    # Show config & current status
python lock_guard.py --help      # Usage help
```

## ⚙️ Configuration

Edit `config.json`:

```json
{
    "password": "unlock123",
    "block_start_time": "22:00",
    "block_end_time": "06:00",
    "esc_count_required": 3,
    "password_timeout_seconds": 15,
    "block_keyboard": true,
    "block_mouse": true,
    "block_wifi": false,
    "block_bluetooth": false,
    "block_usb": false
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `password` | `unlock123` | Secret password to bypass the lock |
| `block_start_time` | `22:00` | Start of blocked window (24-hour format) |
| `block_end_time` | `06:00` | End of blocked window (24-hour format) |
| `esc_count_required` | `3` | ESC presses to enter password mode |
| `password_timeout_seconds` | `15` | Seconds before password entry times out |
| `block_keyboard` | `true` | Enable/disable keyboard blocking |
| `block_mouse` | `true` | Enable/disable mouse blocking |
| `block_wifi` | `false` | Enable/disable WiFi control (needs admin) |
| `block_bluetooth` | `false` | Enable/disable Bluetooth control (needs admin) |
| `block_usb` | `false` | Enable/disable USB storage blocking (needs admin) |

### Time Window Examples

| Start | End | Effect |
|-------|-----|--------|
| `22:00` | `06:00` | Blocks overnight (10 PM → 6 AM) |
| `09:00` | `17:00` | Blocks during work hours |
| `00:00` | `23:59` | Blocks all day |

## 🔑 How to Bypass the Lock

When modules are blocked:

1. **Press ESC 3 times** (or configured count)
2. **Type your password** (invisible — captured silently)
3. **Press Enter**
4. ✅ Correct → all modules unblocked
5. ❌ Wrong → resets back to blocked mode

> **Tip:** Use **Backspace** to correct mistakes. Press **ESC** to cancel password entry.

## 🖥️ Platform Support

| Platform | Session Detection | Keyboard | Mouse | WiFi | Bluetooth | USB |
|----------|-------------------|----------|-------|------|-----------|-----|
| **Windows** | ✅ WTS API | ✅ | ✅ | ✅ netsh | ✅ PowerShell | ✅ Registry |
| **macOS** | ✅ Quartz | ✅ | ✅ | ✅ networksetup | ⚠️ blueutil | ⚠️ Limited |
| **Linux** | ✅ loginctl | ✅ | ✅ | ✅ nmcli | ✅ rfkill | ✅ udisksctl |

### Platform Notes

- **Windows**: May require Administrator for WiFi/Bluetooth/USB control
- **macOS**: Requires Accessibility permissions; Bluetooth needs `blueutil` (`brew install blueutil`)
- **Linux**: May need `sudo` for hardware control; some DEs need X11 access

## 📁 Files

```
├── lock_guard.py       # Main application (all modules)
├── config.json         # Configuration
├── requirements.txt    # Python dependencies
├── run_guard.bat       # Windows standalone launcher
├── run_guard.sh        # macOS/Linux standalone launcher
├── README.md           # This file
└── logs/
    └── lock_guard.log  # Runtime logs
```

## 📋 Log Output

Logs use structured formatting with clear sections:

```
┌──────────────────────────────────────────────────────────────┐
│      🔒  SYSTEM LOCK GUARD  v2.0                             │
│      Cross-Platform Multi-Module Blocker                     │
└──────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📋  CONFIGURATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Platform        : Windows
  Block Window    : 22:00 → 06:00
  MODULE STATUS:
    ⌨  Keyboard   : ✔ ENABLED
    🖱  Mouse      : ✔ ENABLED
    📶 WiFi       : ✘ disabled
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## ⚠️ Important Notes

1. **Keep `config.json` safe** — anyone who reads it can bypass the lock
2. **Test first** — use `--test` mode to verify before relying on it
3. **Don't lose the password** — if forgotten, kill the Python process via Task Manager
4. **Admin required** — WiFi, Bluetooth, and USB control need elevated privileges

## 🛑 Emergency: How to Stop

1. **Ctrl+Alt+Del** → Task Manager → End `python` process
2. Close the command prompt window running the guard
3. On Linux: `killall python3` from another terminal
