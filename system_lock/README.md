# 🔒 System Lock Guard

A **cross-platform** keyboard blocker that activates when your system is unlocked during a configured time window. No popups, no dialogs — the keyboard simply stops working until the secret bypass pattern is entered.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🕐 **Time-based blocking** | Configure a time window (e.g., 10 PM – 6 AM) during which the keyboard is blocked |
| 🔓 **Session-aware** | Detects system unlock events and activates blocking automatically |
| 🔑 **Secret bypass** | Press ESC 3 times → type password → Enter to unlock |
| 🖥️ **Cross-platform** | Works on Windows, macOS, and Linux |
| 🐭 **Mouse unaffected** | Only the keyboard is blocked; mouse works normally |
| 👻 **Invisible** | No popups or visual hints — stealth operation |

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** installed and on PATH

### Installation

```bash
# Clone or download the project, then:
pip install -r requirements.txt
```

### Running

**Windows:**
```batch
run_guard.bat
```

**macOS / Linux:**
```bash
chmod +x run_guard.sh
./run_guard.sh
```

**Direct Python:**
```bash
python lock_guard.py           # Normal mode
python lock_guard.py --test    # Test mode (blocks keyboard immediately)
python lock_guard.py --status  # Show current config & status
```

## ⚙️ Configuration

Edit `config.json` in the project directory:

```json
{
    "password": "unlock123",
    "block_start_time": "22:00",
    "block_end_time": "06:00",
    "esc_count_required": 3,
    "password_timeout_seconds": 15
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `password` | `unlock123` | Secret password to bypass the lock |
| `block_start_time` | `22:00` | Start of blocked window (24-hour format) |
| `block_end_time` | `06:00` | End of blocked window (24-hour format) |
| `esc_count_required` | `3` | Number of ESC presses to enter password mode |
| `password_timeout_seconds` | `15` | Seconds before password entry times out |

### Time Window Examples

| Start | End | Effect |
|-------|-----|--------|
| `22:00` | `06:00` | Blocks overnight (10 PM → 6 AM) |
| `09:00` | `17:00` | Blocks during work hours |
| `00:00` | `23:59` | Blocks all day |

## 🔑 How to Bypass the Lock

When the keyboard is blocked:

1. **Press ESC 3 times** (or the configured count)
2. **Type your password** (nothing will appear on screen — it's captured silently)
3. **Press Enter**
4. ✅ If correct → keyboard is restored
5. ❌ If wrong → resets back to blocked mode

> **Tip:** During password entry, use **Backspace** to correct mistakes. Press **ESC** to cancel and go back to blocked mode.

## 🖥️ Platform Support

| Platform | Session Detection | Keyboard Blocking |
|----------|-------------------|-------------------|
| **Windows** | ✅ WTS API (native) | ✅ pynput |
| **macOS** | ✅ Quartz API | ✅ pynput |
| **Linux** | ✅ loginctl | ✅ pynput |

### Platform-Specific Notes

- **Windows**: May require running as Administrator for full keyboard hook access
- **macOS**: Requires Accessibility permissions (System Preferences → Security & Privacy → Privacy → Accessibility)
- **Linux**: May need to be run with `sudo` for keyboard hook access. Some desktop environments may need `xinput` or X11 access

## 📁 Project Structure

```
├── lock_guard.py       # Main application
├── config.json         # Configuration file
├── requirements.txt    # Python dependencies
├── run_guard.bat       # Windows launcher
├── run_guard.sh        # macOS/Linux launcher
├── README.md           # This file
└── logs/
    └── lock_guard.log  # Runtime logs
```

## 📋 Logs

Logs are written to `logs/lock_guard.log` and also printed to the console. The log captures:
- System lock/unlock events
- Keyboard block/unblock events
- Failed and successful bypass attempts
- Errors and warnings

## ⚠️ Important Notes

1. **Keep `config.json` safe** — anyone who reads it can bypass the lock
2. **Test first** — use `--test` mode to verify it works before relying on it
3. **Don't lose the password** — if you forget it, you'll need to kill the Python process via Task Manager (Ctrl+Alt+Del still works)
4. **mouse always works** — the lock is keyboard-only by design

## 🛑 Emergency: How to Stop

If you need to stop the program:

1. **Ctrl+Alt+Del** → Task Manager → End `python` or `pythonw` process
2. Or close the command prompt window running the guard
3. On Linux: `killall python3` from another terminal
