"""
╔══════════════════════════════════════════════════════════════════╗
║                    SYSTEM LOCK GUARD                             ║
║         Cross-Platform Keyboard Blocker on System Unlock         ║
║                                                                  ║
║  Blocks keyboard during configured time windows.                 ║
║  Bypass: Press ESC 3 times, then type the secret password.       ║
╚══════════════════════════════════════════════════════════════════╝

Platform Support:
  - Windows : Full support (session unlock detection + keyboard block)
  - macOS   : Full support (session unlock detection + keyboard block)
  - Linux   : Time-based blocking (keyboard block via pynput)

Requirements:
  pip install pynput

Usage:
  python lock_guard.py              # Run normally
  python lock_guard.py --test       # Run in test mode (block immediately)
  python lock_guard.py --status     # Check if another instance is running
"""

import json
import os
import sys
import time
import threading
import platform
import signal
import logging
from datetime import datetime, timedelta
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

# ─── Configuration ────────────────────────────────────────────────────────────

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "password": "unlock123",
    "block_start_time": "22:00",
    "block_end_time": "06:00",
    "esc_count_required": 3,
    "password_timeout_seconds": 15,
}


def load_config():
    """Load configuration from config.json, falling back to defaults."""
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update(user_config)
            logger.info("Configuration loaded from %s", CONFIG_FILE)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to load config: %s. Using defaults.", e)
    else:
        logger.info("No config.json found. Using default configuration.")
        # Write default config for user reference
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            logger.info("Default config.json created at %s", CONFIG_FILE)
        except IOError:
            pass
    return config


# ─── Time Window Checker ──────────────────────────────────────────────────────


def parse_time(time_str):
    """Parse a time string like '22:00' into hour and minute."""
    parts = time_str.strip().split(":")
    return int(parts[0]), int(parts[1])


def is_in_blocked_window(config):
    """Check if the current time falls within the blocked window."""
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute

    start_h, start_m = parse_time(config["block_start_time"])
    end_h, end_m = parse_time(config["block_end_time"])

    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes <= end_minutes:
        # Same-day window (e.g., 09:00 to 17:00)
        return start_minutes <= current_minutes < end_minutes
    else:
        # Overnight window (e.g., 22:00 to 06:00)
        return current_minutes >= start_minutes or current_minutes < end_minutes


# ─── Keyboard Blocker (Cross-Platform via pynput) ─────────────────────────────


class KeyboardBlocker:
    """
    Blocks all keyboard input using pynput.

    Bypass mechanism:
      1. Press ESC the configured number of times (default: 3)
      2. Type the secret password
      3. Press Enter

    If the password is correct, the keyboard is unblocked.
    If wrong, it resets and continues blocking.
    """

    def __init__(self, config, on_unlock_callback=None):
        self.config = config
        self.password = config["password"]
        self.esc_required = config.get("esc_count_required", 3)
        self.password_timeout = config.get("password_timeout_seconds", 15)
        self.on_unlock_callback = on_unlock_callback

        # State
        self._blocking = False
        self._esc_count = 0
        self._in_password_mode = False
        self._password_buffer = []
        self._last_key_time = None
        self._listener = None
        self._lock = threading.Lock()

        # Import pynput here to fail early with a clear message
        try:
            from pynput import keyboard
            self._keyboard_module = keyboard
        except ImportError:
            logger.error(
                "╔══════════════════════════════════════════════════════╗\n"
                "║  pynput is not installed!                            ║\n"
                "║  Run: pip install pynput                             ║\n"
                "╚══════════════════════════════════════════════════════╝"
            )
            sys.exit(1)

    def start_blocking(self):
        """Start blocking keyboard input."""
        with self._lock:
            if self._blocking:
                logger.info("Keyboard is already blocked.")
                return

            self._blocking = True
            self._esc_count = 0
            self._in_password_mode = False
            self._password_buffer = []
            self._last_key_time = None

        logger.info("═══════════════════════════════════════════════")
        logger.info("  KEYBOARD BLOCKED — All keys are suppressed")
        logger.info("  Bypass: Press ESC %d times → type password → Enter", self.esc_required)
        logger.info("═══════════════════════════════════════════════")

        # Start listener with suppress=True to block all keys
        self._listener = self._keyboard_module.Listener(
            on_press=self._on_key_press,
            suppress=True,
        )
        self._listener.daemon = True
        self._listener.start()

        # Start password timeout checker
        self._timeout_thread = threading.Thread(target=self._check_password_timeout, daemon=True)
        self._timeout_thread.start()

    def stop_blocking(self):
        """Stop blocking keyboard input (restore full access)."""
        with self._lock:
            if not self._blocking:
                return
            self._blocking = False

        if self._listener:
            self._listener.stop()
            self._listener = None

        logger.info("═══════════════════════════════════════════════")
        logger.info("  KEYBOARD UNBLOCKED — Full access restored")
        logger.info("═══════════════════════════════════════════════")

        if self.on_unlock_callback:
            self.on_unlock_callback()

    @property
    def is_blocking(self):
        return self._blocking

    def _on_key_press(self, key):
        """Handle a key press while blocking.
        
        IMPORTANT: With suppress=True, ALL keys are already blocked.
        - Return None → key stays suppressed (this is what we want)
        - Return False → STOPS the entire listener (only do this to unblock)
        """
        keyboard = self._keyboard_module

        with self._lock:
            if not self._blocking:
                return  # Not blocking, but suppress=True still eats the key

            self._last_key_time = time.time()

            # ─── Password entry mode ───
            if self._in_password_mode:
                self._handle_password_key(key, keyboard)
                return  # Key stays suppressed

            # ─── Normal blocking mode — count ESC presses ───
            if key == keyboard.Key.esc:
                self._esc_count += 1
                remaining = self.esc_required - self._esc_count
                if remaining > 0:
                    logger.debug("ESC pressed (%d/%d)", self._esc_count, self.esc_required)
                if self._esc_count >= self.esc_required:
                    self._in_password_mode = True
                    self._password_buffer = []
                    logger.info("Password mode activated — type your password and press Enter")
            else:
                # Any non-ESC key resets the ESC counter
                self._esc_count = 0

            # Key stays suppressed (return None)
            return

    def _handle_password_key(self, key, keyboard):
        """Handle key press during password entry mode.
        
        Does NOT return a value — the caller handles return.
        When password is correct, schedules unblock on a separate thread
        to avoid deadlock (we're inside self._lock).
        """

        # Enter → check password
        if key == keyboard.Key.enter:
            entered = "".join(self._password_buffer)
            if entered == self.password:
                logger.info("✓ Correct password entered!")
                # Schedule unblock on a separate thread to avoid deadlock
                # (we're currently holding self._lock)
                threading.Thread(target=self.stop_blocking, daemon=True).start()
            else:
                logger.warning("✗ Wrong password. Resetting to block mode.")
                self._in_password_mode = False
                self._esc_count = 0
                self._password_buffer = []
            return

        # Backspace → remove last character
        if key == keyboard.Key.backspace:
            if self._password_buffer:
                self._password_buffer.pop()
            return

        # Escape → cancel password entry
        if key == keyboard.Key.esc:
            logger.info("Password entry cancelled.")
            self._in_password_mode = False
            self._esc_count = 0
            self._password_buffer = []
            return

        # Regular character → add to buffer
        try:
            char = key.char
            if char is not None:
                self._password_buffer.append(char)
                # Show masked progress
                logger.debug("Password: %s", "*" * len(self._password_buffer))
        except AttributeError:
            # Special key (Shift, Ctrl, etc.) — ignore silently
            pass

    def _check_password_timeout(self):
        """Reset password mode if no key is pressed for the timeout duration."""
        while self._blocking:
            time.sleep(1)
            with self._lock:
                if (
                    self._in_password_mode
                    and self._last_key_time is not None
                    and time.time() - self._last_key_time > self.password_timeout
                ):
                    logger.info("Password entry timed out. Resetting.")
                    self._in_password_mode = False
                    self._esc_count = 0
                    self._password_buffer = []


# ─── Session Monitor (Platform-Specific) ──────────────────────────────────────


class SessionMonitor:
    """
    Monitors system lock/unlock events.
    Uses platform-specific APIs with a common interface.
    """

    def __init__(self, on_unlock_callback, on_lock_callback=None):
        self.on_unlock = on_unlock_callback
        self.on_lock = on_lock_callback
        self._running = False
        self._system = platform.system()

    def start(self):
        """Start monitoring for session changes."""
        self._running = True
        logger.info("Session monitor starting on %s platform...", self._system)

        if self._system == "Windows":
            self._start_windows()
        elif self._system == "Darwin":
            self._start_macos()
        elif self._system == "Linux":
            self._start_linux()
        else:
            logger.warning("Unsupported platform: %s. Using time-based fallback.", self._system)
            self._start_fallback()

    def stop(self):
        """Stop monitoring."""
        self._running = False
        logger.info("Session monitor stopped.")

    # ─── Windows ───────────────────────────────────────────────────────────

    def _start_windows(self):
        """Monitor session events on Windows using WTS notifications."""
        thread = threading.Thread(target=self._windows_session_thread, daemon=True)
        thread.start()

    def _windows_session_thread(self):
        """Windows session monitoring using ctypes and a hidden window."""
        try:
            import ctypes
            import ctypes.wintypes as wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            wtsapi32 = ctypes.windll.wtsapi32

            # Constants
            WM_WTSSESSION_CHANGE = 0x02B1
            WTS_SESSION_LOCK = 0x7
            WTS_SESSION_UNLOCK = 0x8
            NOTIFY_FOR_THIS_SESSION = 0
            WM_DESTROY = 0x0002
            WM_QUIT = 0x0012
            WS_EX_TOOLWINDOW = 0x00000080

            # Window procedure
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                wintypes.HWND,
                ctypes.c_uint,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )

            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == WM_WTSSESSION_CHANGE:
                    if wparam == WTS_SESSION_UNLOCK:
                        logger.info("◆ System UNLOCKED detected")
                        if self.on_unlock:
                            self.on_unlock()
                    elif wparam == WTS_SESSION_LOCK:
                        logger.info("◆ System LOCKED detected")
                        if self.on_lock:
                            self.on_lock()
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

            callback = WNDPROC(wnd_proc)

            # Register window class
            wc = wintypes.WNDCLASSW()
            wc.lpfnWndProc = callback
            wc.lpszClassName = "LockGuardSessionMonitor"
            wc.hInstance = kernel32.GetModuleHandleW(None)

            class_atom = user32.RegisterClassW(ctypes.byref(wc))
            if not class_atom:
                logger.error("Failed to register window class: %s", ctypes.GetLastError())
                return

            # Create hidden window
            hwnd = user32.CreateWindowExW(
                WS_EX_TOOLWINDOW,
                wc.lpszClassName,
                "LockGuard Hidden Window",
                0,  # No visible style
                0, 0, 0, 0,
                None, None, wc.hInstance, None,
            )

            if not hwnd:
                logger.error("Failed to create hidden window: %s", ctypes.GetLastError())
                return

            # Register for session notifications
            if not wtsapi32.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION):
                logger.error("Failed to register for session notifications")
                user32.DestroyWindow(hwnd)
                return

            logger.info("Windows session monitor active (hidden window created)")

            # Message loop
            msg = wintypes.MSG()
            while self._running:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result == 0 or result == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            # Cleanup
            wtsapi32.WTSUnRegisterSessionNotification(hwnd)
            user32.DestroyWindow(hwnd)

        except Exception as e:
            logger.error("Windows session monitor error: %s", e)
            logger.info("Falling back to time-based monitoring.")
            self._start_fallback()

    # ─── macOS ─────────────────────────────────────────────────────────────

    def _start_macos(self):
        """Monitor session events on macOS using distributed notifications."""
        thread = threading.Thread(target=self._macos_session_thread, daemon=True)
        thread.start()

    def _macos_session_thread(self):
        """macOS session monitoring using CoreFoundation distributed notifications."""
        try:
            import subprocess

            logger.info("macOS session monitor active (polling screen lock state)")

            was_locked = False
            while self._running:
                try:
                    # Check if screen is locked using Quartz
                    result = subprocess.run(
                        [
                            "python3", "-c",
                            "import Quartz; "
                            "d=Quartz.CGSessionCopyCurrentDictionary(); "
                            "print(d.get('CGSSessionScreenIsLocked', 0))"
                        ],
                        capture_output=True, text=True, timeout=5,
                    )
                    is_locked = result.stdout.strip() == "1"

                    if was_locked and not is_locked:
                        logger.info("◆ System UNLOCKED detected (macOS)")
                        if self.on_unlock:
                            self.on_unlock()
                    elif not was_locked and is_locked:
                        logger.info("◆ System LOCKED detected (macOS)")
                        if self.on_lock:
                            self.on_lock()

                    was_locked = is_locked

                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

                time.sleep(2)

        except Exception as e:
            logger.error("macOS session monitor error: %s", e)
            self._start_fallback()

    # ─── Linux ──────────────────────────────────────────────────────────────

    def _start_linux(self):
        """Monitor session events on Linux using D-Bus."""
        thread = threading.Thread(target=self._linux_session_thread, daemon=True)
        thread.start()

    def _linux_session_thread(self):
        """Linux session monitoring using D-Bus screensaver signals."""
        try:
            import subprocess

            logger.info("Linux session monitor active (polling via loginctl)")

            was_locked = False
            while self._running:
                try:
                    # Use loginctl to check session state
                    result = subprocess.run(
                        ["loginctl", "show-session", "self", "-p", "LockedHint", "--value"],
                        capture_output=True, text=True, timeout=5,
                    )
                    is_locked = result.stdout.strip().lower() == "yes"

                    if was_locked and not is_locked:
                        logger.info("◆ System UNLOCKED detected (Linux)")
                        if self.on_unlock:
                            self.on_unlock()
                    elif not was_locked and is_locked:
                        logger.info("◆ System LOCKED detected (Linux)")
                        if self.on_lock:
                            self.on_lock()

                    was_locked = is_locked

                except (subprocess.TimeoutExpired, FileNotFoundError):
                    pass

                time.sleep(2)

        except Exception as e:
            logger.error("Linux session monitor error: %s", e)
            self._start_fallback()

    # ─── Fallback (all platforms) ───────────────────────────────────────────

    def _start_fallback(self):
        """Fallback: Just trigger unlock callback immediately (time-based only)."""
        logger.info("Using fallback mode — triggering on time-window check only.")
        if self.on_unlock:
            self.on_unlock()


# ─── Main Application ─────────────────────────────────────────────────────────


class LockGuardApp:
    """
    Main application that ties together:
      - Configuration loading
      - Session monitoring (lock/unlock detection)
      - Time window checking
      - Keyboard blocking with ESC×3 + password bypass
    """

    def __init__(self, test_mode=False):
        self.config = load_config()
        self.test_mode = test_mode
        self._running = False

        # Keyboard blocker
        self.blocker = KeyboardBlocker(
            config=self.config,
            on_unlock_callback=self._on_keyboard_unlocked,
        )

        # Session monitor
        self.session_monitor = SessionMonitor(
            on_unlock_callback=self._on_system_unlocked,
            on_lock_callback=self._on_system_locked,
        )

        # Time-based re-check thread
        self._time_check_thread = None

    def start(self):
        """Start the Lock Guard application."""
        self._running = True

        self._print_banner()
        logger.info("Platform: %s", platform.system())
        logger.info("Blocked time window: %s → %s",
                     self.config["block_start_time"],
                     self.config["block_end_time"])
        logger.info("ESC presses required: %d", self.config.get("esc_count_required", 3))
        logger.info("Password timeout: %ds", self.config.get("password_timeout_seconds", 15))

        if self.test_mode:
            logger.info("╔══════════════════════════════════════════╗")
            logger.info("║        RUNNING IN TEST MODE              ║")
            logger.info("║  Keyboard will be blocked immediately!   ║")
            logger.info("║  Press ESC %d times + password to unlock  ║",
                        self.config.get("esc_count_required", 3))
            logger.info("╚══════════════════════════════════════════╝")
            time.sleep(2)
            self.blocker.start_blocking()
        else:
            # Start session monitor
            self.session_monitor.start()

            # Start periodic time-window check
            self._time_check_thread = threading.Thread(
                target=self._periodic_time_check, daemon=True
            )
            self._time_check_thread.start()

            # Also check immediately on startup
            if is_in_blocked_window(self.config):
                logger.info("Current time is within blocked window. Activating keyboard block.")
                self.blocker.start_blocking()

        # Keep the main thread alive
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interrupted by user (Ctrl+C)")
            self.stop()

    def stop(self):
        """Stop everything gracefully."""
        self._running = False
        self.blocker.stop_blocking()
        self.session_monitor.stop()
        logger.info("Lock Guard stopped. Goodbye!")

    def _on_system_unlocked(self):
        """Called when the system is unlocked."""
        if self.test_mode:
            return

        if is_in_blocked_window(self.config):
            logger.info("System unlocked during blocked window → Blocking keyboard")
            if not self.blocker.is_blocking:
                self.blocker.start_blocking()
        else:
            logger.info("System unlocked outside blocked window → No action needed")

    def _on_system_locked(self):
        """Called when the system is locked."""
        # Stop blocking while the system is locked (no point)
        if self.blocker.is_blocking:
            logger.info("System locked → Temporarily pausing keyboard block")
            self.blocker.stop_blocking()

    def _on_keyboard_unlocked(self):
        """Called when the user successfully entered the password."""
        logger.info("User bypassed the lock with correct password. Full access granted.")

    def _periodic_time_check(self):
        """Periodically check if we're in the blocked window and act accordingly."""
        while self._running:
            time.sleep(30)  # Check every 30 seconds

            if self.test_mode:
                continue

            in_window = is_in_blocked_window(self.config)

            if not in_window and self.blocker.is_blocking:
                logger.info("Blocked time window ended → Unblocking keyboard automatically")
                self.blocker.stop_blocking()

    def _print_banner(self):
        banner = """
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              ╔═╗╦ ╦╔═╗╔╦╗╔═╗╔╦╗                                ║
║              ╚═╗╚╦╝╚═╗ ║ ║╣ ║║║                                ║
║              ╚═╝ ╩ ╚═╝ ╩ ╚═╝╩ ╩                                ║
║                                                                  ║
║                   LOCK  GUARD  v1.0                              ║
║           Cross-Platform Keyboard Blocker                        ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Blocks keyboard during configured time windows.                ║
║  Bypass: Press ESC × N  →  type password  →  Enter              ║
╚══════════════════════════════════════════════════════════════════╝
        """
        for line in banner.strip().split("\n"):
            logger.info(line)


# ─── CLI Entry Point ──────────────────────────────────────────────────────────


def print_usage():
    """Print command-line usage."""
    print("""
System Lock Guard — Usage:

  python lock_guard.py              Run the lock guard (normal mode)
  python lock_guard.py --test       Test mode: block keyboard immediately
  python lock_guard.py --status     Show current configuration
  python lock_guard.py --help       Show this help message

Configuration:
  Edit config.json in the same directory as this script.

  {
      "password": "unlock123",         // Bypass password
      "block_start_time": "22:00",     // Block window start (24h)
      "block_end_time": "06:00",       // Block window end (24h)
      "esc_count_required": 3,         // ESC presses to enter password mode
      "password_timeout_seconds": 15   // Timeout for password entry
  }
""")


def print_status():
    """Print current configuration and status."""
    config = load_config()
    in_window = is_in_blocked_window(config)
    now = datetime.now().strftime("%H:%M:%S")

    print(f"""
╔══════════════════════════════════════════════════╗
║              Lock Guard Status                   ║
╠══════════════════════════════════════════════════╣
║  Platform        : {platform.system():<28}║
║  Current Time    : {now:<28}║
║  Block Window    : {config['block_start_time']} → {config['block_end_time']:<20}║
║  In Window Now?  : {'YES — keyboard WILL be blocked' if in_window else 'NO — keyboard is free':<28}║
║  Password        : {'*' * len(config['password']):<28}║
║  ESC Count       : {config.get('esc_count_required', 3):<28}║
║  Password Timeout: {str(config.get('password_timeout_seconds', 15)) + 's':<28}║
╚══════════════════════════════════════════════════╝
""")


def main():
    """Main entry point."""
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print_usage()
        return

    if "--status" in args:
        print_status()
        return

    test_mode = "--test" in args

    # Handle graceful shutdown
    app = LockGuardApp(test_mode=test_mode)

    def signal_handler(sig, frame):
        logger.info("Received signal %s. Shutting down...", sig)
        app.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        app.start()
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        app.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
