"""
╔══════════════════════════════════════════════════════════════════╗
║                    SYSTEM LOCK GUARD  v2.0                       ║
║         Cross-Platform Multi-Module Blocker on System Unlock     ║
║                                                                  ║
║  Blocks keyboard, mouse, WiFi, Bluetooth, USB during time        ║
║  windows when the system is unlocked.                            ║
║                                                                  ║
║  Bypass: Press ESC N times → type password → Enter               ║
╚══════════════════════════════════════════════════════════════════╝

Supported blocking modules (configure via config.json):
  - block_keyboard  : Suppress all key presses
  - block_mouse     : Suppress all mouse movement and clicks
  - block_wifi      : Disable / re-enable Wi-Fi adapter
  - block_bluetooth : Disable / re-enable Bluetooth adapter
  - block_usb       : Disable USB storage devices (Windows only)

Platform Support:
  Windows : All modules supported
  macOS   : keyboard, mouse, wifi, bluetooth
  Linux   : keyboard, mouse, wifi, bluetooth

Requirements:
  pip install pynput

Usage:
  python lock_guard.py              Normal mode
  python lock_guard.py --test       Block immediately (test)
  python lock_guard.py --status     Show config & current state
  python lock_guard.py --help       Show usage
"""

import json
import os
import sys
import time
import threading
import platform
import signal
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# ─── Logging Setup ────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "lock_guard.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("LockGuard")

SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"

# ─── Configuration ────────────────────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "password": "unlock123",
    "block_start_time": "22:00",
    "block_end_time": "06:00",
    "esc_count_required": 3,
    "password_timeout_seconds": 15,
    # Module toggles
    "block_keyboard": True,
    "block_mouse": True,
    "block_wifi": False,
    "block_bluetooth": False,
    "block_usb": False,
}


def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
            logger.info("Config loaded from %s", CONFIG_FILE)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Config load failed: %s — using defaults.", e)
    else:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            logger.info("Default config.json created at %s", CONFIG_FILE)
        except IOError:
            pass
    return config


# ─── Time Window Checker ──────────────────────────────────────────────────────


def _parse_time(time_str):
    h, m = time_str.strip().split(":")
    return int(h) * 60 + int(m)


def is_in_blocked_window(config):
    now = datetime.now()
    current = now.hour * 60 + now.minute
    start = _parse_time(config["block_start_time"])
    end = _parse_time(config["block_end_time"])
    if start <= end:
        return start <= current < end          # Same-day window
    return current >= start or current < end   # Overnight window


# ─── Helper: Run subprocess quietly ──────────────────────────────────────────


def _run(cmd, check=False, timeout=10):
    """Run a shell command silently. Returns (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if SYSTEM == "Windows" else 0,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("_run %s failed: %s", cmd, e)
        return -1, "", str(e)


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 1 — KEYBOARD BLOCKER
# ═════════════════════════════════════════════════════════════════════════════

class KeyboardBlocker:
    """
    Suppresses all keyboard input via pynput (suppress=True).
    Bypass: ESC × N  →  type password  →  Enter
    """

    def __init__(self, config, on_unlocked=None):
        self.password       = config["password"]
        self.esc_required   = config.get("esc_count_required", 3)
        self.pwd_timeout    = config.get("password_timeout_seconds", 15)
        self.on_unlocked    = on_unlocked

        self._blocking      = False
        self._esc_count     = 0
        self._in_pwd_mode   = False
        self._pwd_buffer    = []
        self._last_key_t    = None
        self._listener      = None
        self._lock          = threading.Lock()

        try:
            from pynput import keyboard
            self._kb = keyboard
        except ImportError:
            logger.error("pynput not installed. Run: pip install pynput")
            sys.exit(1)

    # ── Public API ───────────────────────────────────────────────────────────

    def start(self):
        with self._lock:
            if self._blocking:
                return
            self._blocking    = True
            self._esc_count   = 0
            self._in_pwd_mode = False
            self._pwd_buffer  = []
            self._last_key_t  = None

        logger.info("⌨  KEYBOARD BLOCKED — ESC×%d then password to unlock", self.esc_required)

        self._listener = self._kb.Listener(
            on_press=self._on_press,
            suppress=True,
        )
        self._listener.daemon = True
        self._listener.start()

        threading.Thread(target=self._timeout_watcher, daemon=True).start()

    def stop(self):
        with self._lock:
            if not self._blocking:
                return
            self._blocking = False

        if self._listener:
            self._listener.stop()
            self._listener = None
        logger.info("⌨  KEYBOARD UNBLOCKED")
        if self.on_unlocked:
            self.on_unlocked()

    @property
    def active(self):
        return self._blocking

    # ── Key handler ──────────────────────────────────────────────────────────

    def _on_press(self, key):
        """
        Called for every key. With suppress=True all keys are already eaten.
        Returning None  → key stays suppressed (normal blocked state).
        Returning False → stops the listener entirely (we only do this on unlock).
        """
        with self._lock:
            if not self._blocking:
                return

            self._last_key_t = time.time()

            if self._in_pwd_mode:
                self._handle_pwd_key(key)
                return

            if key == self._kb.Key.esc:
                self._esc_count += 1
                logger.debug("ESC %d/%d", self._esc_count, self.esc_required)
                if self._esc_count >= self.esc_required:
                    self._in_pwd_mode = True
                    self._pwd_buffer  = []
                    logger.info("  → Password mode ON — type password + Enter")
            else:
                self._esc_count = 0

    def _handle_pwd_key(self, key):
        kb = self._kb
        if key == kb.Key.enter:
            entered = "".join(self._pwd_buffer)
            if entered == self.password:
                logger.info("✓ Correct password!")
                threading.Thread(target=self.stop, daemon=True).start()
            else:
                logger.warning("✗ Wrong password — reset")
                self._in_pwd_mode = False
                self._esc_count   = 0
                self._pwd_buffer  = []
        elif key == kb.Key.backspace:
            if self._pwd_buffer:
                self._pwd_buffer.pop()
        elif key == kb.Key.esc:
            logger.info("  → Password mode OFF")
            self._in_pwd_mode = False
            self._esc_count   = 0
            self._pwd_buffer  = []
        else:
            try:
                if key.char:
                    self._pwd_buffer.append(key.char)
                    logger.debug("  pwd len=%d", len(self._pwd_buffer))
            except AttributeError:
                pass

    def _timeout_watcher(self):
        while self._blocking:
            time.sleep(1)
            with self._lock:
                if (self._in_pwd_mode
                        and self._last_key_t
                        and time.time() - self._last_key_t > self.pwd_timeout):
                    logger.info("⌛ Password entry timed out — reset")
                    self._in_pwd_mode = False
                    self._esc_count   = 0
                    self._pwd_buffer  = []


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 2 — MOUSE BLOCKER
# ═════════════════════════════════════════════════════════════════════════════

class MouseBlocker:
    """Suppresses all mouse movement and clicks via pynput (suppress=True)."""

    def __init__(self):
        self._blocking  = False
        self._listener  = None

        try:
            from pynput import mouse
            self._mouse = mouse
        except ImportError:
            logger.error("pynput not installed. Run: pip install pynput")
            sys.exit(1)

    def start(self):
        if self._blocking:
            return
        self._blocking = True

        self._listener = self._mouse.Listener(
            on_move=self._block,
            on_click=self._block,
            on_scroll=self._block,
            suppress=True,
        )
        self._listener.daemon = True
        self._listener.start()
        logger.info("🖱  MOUSE BLOCKED")

    def stop(self):
        if not self._blocking:
            return
        self._blocking = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        logger.info("🖱  MOUSE UNBLOCKED")

    @property
    def active(self):
        return self._blocking

    def _block(self, *args):
        """Return None to keep suppressing (returning False stops the listener)."""
        return


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 3 — WIFI BLOCKER
# ═════════════════════════════════════════════════════════════════════════════

class WiFiBlocker:
    """Disables / re-enables the Wi-Fi adapter using platform-native commands."""

    def __init__(self):
        self._blocked = False

    def start(self):
        if self._blocked:
            return
        ok = self._set_state(enable=False)
        if ok:
            self._blocked = True
            logger.info("📶  WIFI DISABLED")
        else:
            logger.warning("📶  WIFI disable failed (may need admin / sudo)")

    def stop(self):
        if not self._blocked:
            return
        ok = self._set_state(enable=True)
        if ok:
            self._blocked = False
            logger.info("📶  WIFI ENABLED")
        else:
            logger.warning("📶  WIFI re-enable failed")

    @property
    def active(self):
        return self._blocked

    def _set_state(self, enable: bool) -> bool:
        action = "enable" if enable else "disable"

        if SYSTEM == "Windows":
            # netsh interface set interface "Wi-Fi" enable/disable
            adapters = self._get_wifi_adapters_windows()
            if not adapters:
                logger.warning("No Wi-Fi adapter found via netsh.")
                return False
            success = True
            for adapter in adapters:
                rc, _, _ = _run(
                    ["netsh", "interface", "set", "interface", adapter, action],
                    check=True,
                )
                if rc != 0:
                    success = False
            return success

        elif SYSTEM == "Darwin":  # macOS
            rc, _, _ = _run(["networksetup", f"-setairportpower", "en0", action.replace("enable","on").replace("disable","off")])
            return rc == 0

        elif SYSTEM == "Linux":
            rc, _, _ = _run(["nmcli", "radio", "wifi", "on" if enable else "off"])
            if rc != 0:
                rc, _, _ = _run(["rfkill", "block" if not enable else "unblock", "wifi"])
            return rc == 0

        return False

    def _get_wifi_adapters_windows(self):
        """Return list of Wi-Fi adapter names from netsh."""
        rc, out, _ = _run(["netsh", "interface", "show", "interface"])
        if rc != 0:
            return []
        adapters = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and ("Wi-Fi" in line or "Wireless" in line or "WLAN" in line):
                # Adapter name is everything after the first 3 columns
                name = " ".join(parts[3:])
                adapters.append(name)
        return adapters or ["Wi-Fi"]   # fallback default name


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 4 — BLUETOOTH BLOCKER
# ═════════════════════════════════════════════════════════════════════════════

class BluetoothBlocker:
    """Disables / re-enables the Bluetooth adapter."""

    def __init__(self):
        self._blocked = False

    def start(self):
        if self._blocked:
            return
        ok = self._set_state(enable=False)
        if ok:
            self._blocked = True
            logger.info("🔵  BLUETOOTH DISABLED")
        else:
            logger.warning("🔵  BLUETOOTH disable failed (may need admin / sudo)")

    def stop(self):
        if not self._blocked:
            return
        ok = self._set_state(enable=True)
        if ok:
            self._blocked = False
            logger.info("🔵  BLUETOOTH ENABLED")
        else:
            logger.warning("🔵  BLUETOOTH re-enable failed")

    @property
    def active(self):
        return self._blocked

    def _set_state(self, enable: bool) -> bool:
        if SYSTEM == "Windows":
            # Use PowerShell to toggle Bluetooth radio
            state = "True" if enable else "False"
            script = (
                "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
                "[void][Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime];"
                "$radios = [Windows.Devices.Radios.Radio]::GetRadiosAsync().GetAwaiter().GetResult();"
                f"$bt = $radios | Where-Object {{ $_.Kind -eq 'Bluetooth' }};"
                f"if ($bt) {{ $bt | ForEach-Object {{ $_.SetStateAsync([Windows.Devices.Radios.RadioState]::{('On' if enable else 'Off')}).GetAwaiter().GetResult() }} }}"
            )
            rc, _, _ = _run(["powershell", "-NoProfile", "-Command", script])
            return rc == 0

        elif SYSTEM == "Darwin":
            state_str = "on" if enable else "off"
            rc, _, _ = _run(["blueutil", f"--power", "1" if enable else "0"])
            return rc == 0

        elif SYSTEM == "Linux":
            rc, _, _ = _run(["rfkill", "block" if not enable else "unblock", "bluetooth"])
            return rc == 0

        return False


# ═════════════════════════════════════════════════════════════════════════════
# MODULE 5 — USB BLOCKER
# ═════════════════════════════════════════════════════════════════════════════

class USBBlocker:
    """
    Blocks USB storage device access.

    Windows : Sets USBSTOR service start type to 4 (Disabled)
    Linux   : Blacklists usb-storage module
    macOS   : Not natively scriptable without 3rd-party tools — logs warning
    """

    def __init__(self):
        self._blocked = False

    def start(self):
        if self._blocked:
            return
        ok = self._set_state(enable=False)
        if ok:
            self._blocked = True
            logger.info("🔌  USB STORAGE BLOCKED")
        else:
            logger.warning("🔌  USB STORAGE block failed (needs admin / sudo)")

    def stop(self):
        if not self._blocked:
            return
        ok = self._set_state(enable=True)
        if ok:
            self._blocked = False
            logger.info("🔌  USB STORAGE UNBLOCKED")
        else:
            logger.warning("🔌  USB STORAGE unblock failed")

    @property
    def active(self):
        return self._blocked

    def _set_state(self, enable: bool) -> bool:
        if SYSTEM == "Windows":
            # USBSTOR registry key: Start=3 (enabled), Start=4 (disabled)
            start_val = "3" if enable else "4"
            rc, _, _ = _run([
                "reg", "add",
                r"HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\USBSTOR",
                "/v", "Start", "/t", "REG_DWORD", "/d", start_val, "/f"
            ])
            return rc == 0

        elif SYSTEM == "Linux":
            if enable:
                # Remove blacklist entry and re-load module
                conf = Path("/etc/modprobe.d/lockguard_usb.conf")
                if conf.exists():
                    conf.unlink()
                rc, _, _ = _run(["modprobe", "usb-storage"])
            else:
                conf = Path("/etc/modprobe.d/lockguard_usb.conf")
                conf.write_text("blacklist usb-storage\n")
                rc, _, _ = _run(["rmmod", "usb_storage"])
            return rc == 0

        elif SYSTEM == "Darwin":
            logger.warning("🔌  USB blocking on macOS requires a 3rd-party tool (e.g., BlockBlock). Skipping.")
            return False

        return False


# ═════════════════════════════════════════════════════════════════════════════
# SESSION MONITOR
# ═════════════════════════════════════════════════════════════════════════════

class SessionMonitor:
    """Detects system lock/unlock events, platform-specific."""

    def __init__(self, on_unlock, on_lock=None):
        self.on_unlock  = on_unlock
        self.on_lock    = on_lock
        self._running   = False

    def start(self):
        self._running = True
        logger.info("Session monitor starting (%s)...", SYSTEM)
        if SYSTEM == "Windows":
            threading.Thread(target=self._windows_loop, daemon=True).start()
        elif SYSTEM == "Darwin":
            threading.Thread(target=self._poll_loop,
                             args=("python3 -c \"import Quartz; d=Quartz.CGSessionCopyCurrentDictionary(); print(d.get('CGSSessionScreenIsLocked',0))\"",),
                             daemon=True).start()
        elif SYSTEM == "Linux":
            threading.Thread(target=self._linux_loop, daemon=True).start()
        else:
            logger.warning("Unknown platform — using fallback (trigger unlock now).")
            self._fallback()

    def stop(self):
        self._running = False

    # ── Windows ──────────────────────────────────────────────────────────────

    def _windows_loop(self):
        try:
            import ctypes
            import ctypes.wintypes as wt

            u32    = ctypes.windll.user32
            k32    = ctypes.windll.kernel32
            wts    = ctypes.windll.wtsapi32

            WM_WTSSESSION_CHANGE = 0x02B1
            WTS_UNLOCK = 0x8
            WTS_LOCK   = 0x7
            WS_EX_TOOLWINDOW = 0x00000080
            NOTIFY_FOR_THIS_SESSION = 0

            WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)

            def wnd_proc(hwnd, msg, wp, lp):
                if msg == WM_WTSSESSION_CHANGE:
                    if wp == WTS_UNLOCK:
                        logger.info("◆ UNLOCKED (Windows)")
                        if self.on_unlock:
                            threading.Thread(target=self.on_unlock, daemon=True).start()
                    elif wp == WTS_LOCK:
                        logger.info("◆ LOCKED (Windows)")
                        if self.on_lock:
                            threading.Thread(target=self.on_lock, daemon=True).start()
                    return 0
                return u32.DefWindowProcW(hwnd, msg, wp, lp)

            cb = WNDPROC(wnd_proc)
            wc = wt.WNDCLASSW()
            wc.lpfnWndProc  = cb
            wc.lpszClassName = "LGSessionMon"
            wc.hInstance     = k32.GetModuleHandleW(None)

            if not u32.RegisterClassW(ctypes.byref(wc)):
                raise RuntimeError("RegisterClassW failed")

            hwnd = u32.CreateWindowExW(
                WS_EX_TOOLWINDOW, wc.lpszClassName, "LGHidden",
                0, 0, 0, 0, 0, None, None, wc.hInstance, None,
            )
            if not hwnd:
                raise RuntimeError("CreateWindowExW failed")

            wts.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION)
            logger.info("Windows WTS session monitor active.")

            msg = wt.MSG()
            while self._running:
                r = u32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r == 0 or r == -1:
                    break
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))

            wts.WTSUnRegisterSessionNotification(hwnd)
            u32.DestroyWindow(hwnd)

        except Exception as e:
            logger.error("Windows session monitor error: %s — using fallback poll.", e)
            self._poll_loop_fallback()

    # ── Linux ─────────────────────────────────────────────────────────────────

    def _linux_loop(self):
        was_locked = False
        logger.info("Linux session monitor active (loginctl poll).")
        while self._running:
            try:
                rc, out, _ = _run(["loginctl", "show-session", "self", "-p", "LockedHint", "--value"])
                is_locked = out.lower() == "yes"
                if was_locked and not is_locked:
                    logger.info("◆ UNLOCKED (Linux)")
                    if self.on_unlock:
                        threading.Thread(target=self.on_unlock, daemon=True).start()
                elif not was_locked and is_locked:
                    logger.info("◆ LOCKED (Linux)")
                    if self.on_lock:
                        threading.Thread(target=self.on_lock, daemon=True).start()
                was_locked = is_locked
            except Exception:
                pass
            time.sleep(2)

    # ── macOS / generic poll ──────────────────────────────────────────────────

    def _poll_loop(self, check_cmd):
        was_locked = False
        logger.info("Session monitor active (shell poll).")
        while self._running:
            try:
                rc, out, _ = _run(["sh", "-c", check_cmd])
                is_locked = out.strip() == "1"
                if was_locked and not is_locked:
                    logger.info("◆ UNLOCKED")
                    if self.on_unlock:
                        threading.Thread(target=self.on_unlock, daemon=True).start()
                elif not was_locked and is_locked:
                    logger.info("◆ LOCKED")
                    if self.on_lock:
                        threading.Thread(target=self.on_lock, daemon=True).start()
                was_locked = is_locked
            except Exception:
                pass
            time.sleep(2)

    def _poll_loop_fallback(self):
        """Windows fallback: poll GetLastInputInfo to detect very long idle → treat as locked."""
        logger.info("Using idle-time poll fallback (Windows).")
        # Just trigger unlock immediately so time-based guard works
        self._fallback()

    def _fallback(self):
        logger.info("Fallback: triggering unlock handler now.")
        if self.on_unlock:
            threading.Thread(target=self.on_unlock, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═════════════════════════════════════════════════════════════════════════════

class LockGuardApp:

    def __init__(self, test_mode=False):
        self.config    = load_config()
        self.test_mode = test_mode
        self._running  = False

        # Instantiate blockers (only the enabled ones are started/stopped)
        self.kb_blocker  = KeyboardBlocker(self.config, on_unlocked=self._on_kb_unlocked)
        self.mouse_blocker = MouseBlocker()
        self.wifi_blocker  = WiFiBlocker()
        self.bt_blocker    = BluetoothBlocker()
        self.usb_blocker   = USBBlocker()

        self.session_monitor = SessionMonitor(
            on_unlock=self._on_system_unlocked,
            on_lock=self._on_system_locked,
        )

    # ── Public ───────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._print_banner()
        self._log_config()

        if self.test_mode:
            logger.info("╔══════════════════════════════════════════╗")
            logger.info("║  TEST MODE — blocking all enabled modules ║")
            logger.info("╚══════════════════════════════════════════╝")
            time.sleep(1)
            self._block_all()
        else:
            self.session_monitor.start()
            threading.Thread(target=self._time_check_loop, daemon=True).start()
            if is_in_blocked_window(self.config):
                logger.info("Current time is in blocked window → activating.")
                self._block_all()

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Ctrl+C — stopping.")
            self.stop()

    def stop(self):
        self._running = False
        self._unblock_all()
        self.session_monitor.stop()
        logger.info("Lock Guard stopped. Goodbye!")

    # ── Block / unblock all modules ──────────────────────────────────────────

    def _block_all(self):
        cfg = self.config
        if cfg.get("block_keyboard", True):
            self.kb_blocker.start()
        if cfg.get("block_mouse", False):
            self.mouse_blocker.start()
        if cfg.get("block_wifi", False):
            self.wifi_blocker.start()
        if cfg.get("block_bluetooth", False):
            self.bt_blocker.start()
        if cfg.get("block_usb", False):
            self.usb_blocker.start()

    def _unblock_all(self):
        self.kb_blocker.stop()
        self.mouse_blocker.stop()
        self.wifi_blocker.stop()
        self.bt_blocker.stop()
        self.usb_blocker.stop()

    def _anything_active(self):
        return (
            self.kb_blocker.active
            or self.mouse_blocker.active
            or self.wifi_blocker.active
            or self.bt_blocker.active
            or self.usb_blocker.active
        )

    # ── Session callbacks ────────────────────────────────────────────────────

    def _on_system_unlocked(self):
        if self.test_mode:
            return
        if is_in_blocked_window(self.config):
            logger.info("Unlocked during blocked window → blocking all modules")
            self._block_all()
        else:
            logger.info("Unlocked outside blocked window → no action")

    def _on_system_locked(self):
        if self._anything_active():
            logger.info("System locked → pausing all blocks")
            self._unblock_all()

    def _on_kb_unlocked(self):
        """Called on correct password → unblock everything."""
        logger.info("Password accepted → unblocking all modules")
        self._unblock_all()

    # ── Periodic time check ──────────────────────────────────────────────────

    def _time_check_loop(self):
        while self._running:
            time.sleep(30)
            if not is_in_blocked_window(self.config) and self._anything_active():
                logger.info("Time window ended → unblocking all modules")
                self._unblock_all()

    # ── Banner / logging ─────────────────────────────────────────────────────

    def _log_config(self):
        cfg = self.config
        logger.info("Platform   : %s", SYSTEM)
        logger.info("Window     : %s → %s", cfg["block_start_time"], cfg["block_end_time"])
        logger.info("Keyboard   : %s", "ON" if cfg.get("block_keyboard") else "OFF")
        logger.info("Mouse      : %s", "ON" if cfg.get("block_mouse") else "OFF")
        logger.info("WiFi       : %s", "ON" if cfg.get("block_wifi") else "OFF")
        logger.info("Bluetooth  : %s", "ON" if cfg.get("block_bluetooth") else "OFF")
        logger.info("USB        : %s", "ON" if cfg.get("block_usb") else "OFF")

    def _print_banner(self):
        banner = """
╔══════════════════════════════════════════════════════════════════╗
║           SYSTEM LOCK GUARD v2.0                                 ║
║      Keyboard │ Mouse │ WiFi │ Bluetooth │ USB Blocker            ║
╠══════════════════════════════════════════════════════════════════╣
║  Bypass: Press ESC × N  →  type password  →  Enter               ║
╚══════════════════════════════════════════════════════════════════╝"""
        for line in banner.splitlines():
            logger.info(line)


# ═════════════════════════════════════════════════════════════════════════════
# STATUS / HELP / ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

def print_status():
    config = load_config()
    in_win = is_in_blocked_window(config)
    now    = datetime.now().strftime("%H:%M:%S")
    print(f"""
╔══════════════════════════════════════════════════════════╗
║                  Lock Guard v2.0 — Status                 ║
╠══════════════════════════════════════════════════════════╣
║  Platform      : {SYSTEM:<38}║
║  Current Time  : {now:<38}║
║  Block Window  : {config['block_start_time']} → {config['block_end_time']:<31}║
║  In Window?    : {'YES — active blocking' if in_win else 'NO  — modules free':<38}║
╠══════════════════════════════════════════════════════════╣
║  MODULE TOGGLES (from config.json)                        ║
║  block_keyboard  : {'✔  ENABLED' if config.get('block_keyboard') else '✘  disabled':<36}║
║  block_mouse     : {'✔  ENABLED' if config.get('block_mouse') else '✘  disabled':<36}║
║  block_wifi      : {'✔  ENABLED' if config.get('block_wifi') else '✘  disabled':<36}║
║  block_bluetooth : {'✔  ENABLED' if config.get('block_bluetooth') else '✘  disabled':<36}║
║  block_usb       : {'✔  ENABLED' if config.get('block_usb') else '✘  disabled':<36}║
╠══════════════════════════════════════════════════════════╣
║  Password      : {'*' * len(config['password']):<38}║
║  ESC Count     : {str(config.get('esc_count_required', 3)):<38}║
║  Pwd Timeout   : {str(config.get('password_timeout_seconds', 15)) + 's':<38}║
╚══════════════════════════════════════════════════════════╝
""")


def print_usage():
    print("""
System Lock Guard v2.0 — Usage:

  python lock_guard.py              Normal mode
  python lock_guard.py --test       Block immediately (test all enabled modules)
  python lock_guard.py --status     Show config & current state
  python lock_guard.py --help       This help message

config.json options:
  password              Bypass password (typed after ESC × N)
  block_start_time      Block window start  (24h, e.g. "22:00")
  block_end_time        Block window end    (24h, e.g. "06:00")
  esc_count_required    ESC presses before password prompt  (default: 3)
  password_timeout_seconds  Timeout to cancel password entry (default: 15)

  block_keyboard  true/false   Suppress all key presses
  block_mouse     true/false   Suppress all mouse input
  block_wifi      true/false   Disable Wi-Fi adapter   (needs admin)
  block_bluetooth true/false   Disable Bluetooth       (needs admin)
  block_usb       true/false   Block USB storage       (needs admin)
""")


def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print_usage()
        return
    if "--status" in args:
        print_status()
        return

    test_mode = "--test" in args
    app = LockGuardApp(test_mode=test_mode)

    def _sig(sig, frame):
        logger.info("Signal %s — shutting down.", sig)
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    try:
        app.start()
    except Exception as e:
        logger.critical("Fatal: %s", e, exc_info=True)
        app.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
