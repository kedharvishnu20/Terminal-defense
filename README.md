# 🛡️ Security Suite

A comprehensive security toolkit with **real-time system monitoring** and **automated access control**.

## 📦 Modules

| Module | Description |
|--------|-------------|
| [**Security Monitor**](security_monitor/) | Real-time network, DLL, and drive entropy scanning with a web dashboard and AI analysis |
| [**System Lock Guard**](system_lock/) | Cross-platform keyboard, mouse, WiFi, Bluetooth, and USB blocker with time-based scheduling |

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** installed and on PATH

### One-Command Launch

```batch
start.bat
```

This opens a menu to control everything:

```
  📡 SECURITY MONITOR              🔒 SYSTEM LOCK GUARD
  ─────────────────────             ─────────────────────
  [1] Start Server                  [4] Start (normal)
  [2] Start Scanner Only            [5] Start (test mode)
  [3] Open Dashboard                [6] View Status
                                    [7] Edit Config

  ⚙️ SETUP & UTILITIES
  ─────────────────────
  [8]  Install Dependencies         [11] Clear All Logs
  [9]  View Monitor Logs            [12] Edit Monitor Config
  [10] View Guard Logs              [13] Check Environment
```

### Manual Setup

```bash
# Install all dependencies
pip install -r requirements.txt

# Start Security Monitor
cd security_monitor
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Start Lock Guard (separate terminal)
cd system_lock
python lock_guard.py
```

## 🏗️ Project Structure

```
├── start.bat                   # Unified command center
├── requirements.txt            # All dependencies
├── .gitignore
├── README.md                   # This file
│
├── security_monitor/           # Real-time security scanner
│   ├── main.py                 # FastAPI server + API endpoints
│   ├── monitor.py              # Background scanner (network, DLL, drive)
│   ├── config.json             # Thresholds for entropy & connections
│   ├── requirements.txt        # Module-specific dependencies
│   ├── static/                 # Web dashboard
│   │   └── index.html
│   └── logs/                   # Generated at runtime
│       ├── network_log.jsonl
│       ├── dll_entropy_log.jsonl
│       ├── drive_entropy_log.jsonl
│       └── ai_analysis_log.jsonl
│
└── system_lock/                # Access control blocker
    ├── lock_guard.py           # Main application
    ├── config.json             # Passwords, time windows, module toggles
    ├── requirements.txt        # Module-specific dependencies
    ├── run_guard.bat            # Windows launcher
    ├── run_guard.sh             # macOS/Linux launcher
    ├── README.md               # Detailed module docs
    └── logs/
        └── lock_guard.log
```

## ⚙️ Configuration

### Security Monitor — `security_monitor/config.json`

```json
{
    "high_entropy_threshold": 7.2,
    "high_connection_threshold": 100
}
```

### Lock Guard — `system_lock/config.json`

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

## 📋 License

This project is for educational and personal security use.
