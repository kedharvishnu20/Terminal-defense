"""
monitor.py — Background Security Monitor
=========================================
Continuously monitors:
  1. Network connections & packet stats (via psutil)
  2. DLL file entropy (Shannon entropy of DLL files in System32)
  3. System drive entropy (random file sampling across all drives)

Stores structured logs to:
  logs/network_log.jsonl
  logs/dll_entropy_log.jsonl
  logs/drive_entropy_log.jsonl

Also reads:
  ../system_lock/logs/lock_guard.log  (Lock Guard module logs)
"""

import os
import random
import string
import sys
import math
import json
import time
import logging
import threading
import platform
from datetime import datetime
from pathlib import Path
from collections import Counter

try:
    import psutil
except ImportError:
    print("psutil not installed. Run: pip install psutil")
    sys.exit(1)

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent
LOG_DIR   = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

NET_LOG    = LOG_DIR / "network_log.jsonl"
DLL_LOG    = LOG_DIR / "dll_entropy_log.jsonl"
DRIVE_LOG  = LOG_DIR / "drive_entropy_log.jsonl"

# system_lock log file (sibling project)
LOCK_GUARD_LOG = BASE_DIR.parent / "system_lock" / "logs" / "lock_guard.log"

SYSTEM = platform.system()

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)s │ %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "monitor.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("SecMonitor")

# ─── Shannon Entropy ─────────────────────────────────────────────────────────

def shannon_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of bytes. Range: 0.0 (uniform) – 8.0 (random/encrypted)."""
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum(
        (c / length) * math.log2(c / length)
        for c in counts.values()
        if c > 0
    )

# ─── DLL Scanner ─────────────────────────────────────────────────────────────

DLL_SCAN_DIRS = {
    "Windows": [
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32",
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SysWOW64",
    ],
    "Darwin": [Path("/usr/lib"), Path("/usr/local/lib")],
    "Linux":  [Path("/usr/lib"), Path("/lib"), Path("/usr/local/lib")],
}

DLL_EXTENSIONS = {
    "Windows": [".dll"],
    "Darwin":  [".dylib", ".so"],
    "Linux":   [".so"],
}

HIGH_ENTROPY_THRESHOLD = 7.2   # Above this: suspicious (packed/encrypted)
MAX_DLL_SAMPLE = 30            # Max DLLs to scan per cycle (performance)
MAX_READ_BYTES  = 65536        # Read at most 64 KB per file


def scan_dll_entropy() -> list[dict]:
    """Scan DLL/shared-lib files and return entropy records."""
    dirs       = DLL_SCAN_DIRS.get(SYSTEM, [])
    extensions = DLL_EXTENSIONS.get(SYSTEM, [".dll"])
    results    = []

    file_list = []
    for scan_dir in dirs:
        if not scan_dir.exists():
            continue
        try:
            files = [
                f for f in scan_dir.iterdir()
                if f.is_file() and f.suffix.lower() in extensions
            ]
            file_list.extend(files)
        except PermissionError:
            pass

    # Sort by modification time (newest first) so we catch recent changes
    file_list.sort(key=lambda f: f.stat().st_mtime if f.exists() else 0, reverse=True)

    for dll_path in file_list[:MAX_DLL_SAMPLE]:
        try:
            size = dll_path.stat().st_size
            with open(dll_path, "rb") as fh:
                data = fh.read(MAX_READ_BYTES)
            entropy = shannon_entropy(data)
            record = {
                "timestamp":  datetime.now().isoformat(),
                "type":       "dll_entropy",
                "file":       str(dll_path),
                "name":       dll_path.name,
                "size_bytes": size,
                "entropy":    round(entropy, 4),
                "suspicious": entropy >= HIGH_ENTROPY_THRESHOLD,
                "note":       (
                    "⚠ HIGH ENTROPY — Possible packing/encryption!"
                    if entropy >= HIGH_ENTROPY_THRESHOLD
                    else "Normal"
                ),
            }
            results.append(record)
        except (PermissionError, OSError):
            pass

    return results


# ─── System Drive Entropy Scanner ─────────────────────────────────────────────

DRIVE_SCAN_EXTENSIONS = [
    ".exe", ".dll", ".sys", ".bat", ".cmd", ".ps1", ".vbs",    # executables/scripts
    ".zip", ".rar", ".7z", ".tar", ".gz",                      # archives
    ".doc", ".docx", ".xls", ".xlsx", ".pdf",                   # documents
    ".iso", ".img",                                              # disk images
]
MAX_DRIVE_SAMPLE = 40       # max files to sample per scan cycle
MAX_DRIVE_READ   = 65536    # 64 KB


def _get_drives() -> list[Path]:
    """Return list of mounted drives / root paths."""
    if SYSTEM == "Windows":
        # Check A-Z drive letters
        drives = []
        for letter in string.ascii_uppercase:
            p = Path(f"{letter}:\\")
            if p.exists():
                drives.append(p)
        return drives
    else:
        return [Path("/")]   # Unix-like: scan from root


def _walk_sample_files(roots: list[Path], extensions: list[str], max_files: int) -> list[Path]:
    """Walk drive roots and collect candidate files, then random-sample."""
    candidates = []
    per_root = max(200, max_files * 5)  # collect up to this many candidates

    for root in roots:
        count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(str(root)):
                # Skip large/system directories to keep scans fast
                dir_lower = dirpath.lower()
                skip_dirs = ["$recycle", "windows\\winsxs", "node_modules", ".git",
                             "appdata\\local\\temp", "programdata\\package"]
                if any(s in dir_lower for s in skip_dirs):
                    dirnames.clear()
                    continue

                for fname in filenames:
                    if any(fname.lower().endswith(ext) for ext in extensions):
                        fp = Path(dirpath) / fname
                        candidates.append(fp)
                        count += 1
                        if count >= per_root:
                            break
                if count >= per_root:
                    break
        except (PermissionError, OSError):
            pass

    if len(candidates) > max_files:
        return random.sample(candidates, max_files)
    return candidates


def scan_drive_entropy() -> list[dict]:
    """Sample files across system drives and compute their entropy."""
    drives  = _get_drives()
    samples = _walk_sample_files(drives, DRIVE_SCAN_EXTENSIONS, MAX_DRIVE_SAMPLE)
    results = []

    for fpath in samples:
        try:
            stat = fpath.stat()
            with open(fpath, "rb") as fh:
                data = fh.read(MAX_DRIVE_READ)
            ent = shannon_entropy(data)
            results.append({
                "timestamp":  datetime.now().isoformat(),
                "type":       "drive_entropy",
                "file":       str(fpath),
                "name":       fpath.name,
                "drive":      str(fpath.anchor),
                "size_bytes": stat.st_size,
                "entropy":    round(ent, 4),
                "suspicious": ent >= HIGH_ENTROPY_THRESHOLD,
                "note":       (
                    "⚠ HIGH ENTROPY — Possible packing/encryption!"
                    if ent >= HIGH_ENTROPY_THRESHOLD
                    else "Normal"
                ),
            })
        except (PermissionError, OSError):
            pass

    return results


# ─── Lock Guard Log Reader ────────────────────────────────────────────────────

def read_lock_guard_log(n: int = 100) -> list[dict]:
    """Read the last N lines of the system_lock lock_guard.log text file."""
    if not LOCK_GUARD_LOG.exists():
        return []
    try:
        lines = LOCK_GUARD_LOG.read_text(encoding="utf-8").strip().splitlines()
        result = []
        for line in lines[-n:]:
            # Format: 2026-02-21 21:00:00 │ INFO    │ message
            parts = line.split("│", maxsplit=2)
            if len(parts) >= 3:
                result.append({
                    "timestamp": parts[0].strip(),
                    "level":     parts[1].strip(),
                    "message":   parts[2].strip(),
                })
            else:
                result.append({"timestamp": "", "level": "", "message": line})
        return result
    except (IOError, UnicodeDecodeError):
        return []


# ─── Network Monitor ─────────────────────────────────────────────────────────

_prev_net_io = None

def snapshot_network() -> list[dict]:
    """Capture active network connections and I/O stats."""
    global _prev_net_io
    records = []
    now = datetime.now().isoformat()

    # ── Active connections ──
    try:
        conns = psutil.net_connections(kind="inet")
        conn_summary = []
        for c in conns:
            if c.status and c.status != "NONE":
                conn_summary.append({
                    "laddr": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "—",
                    "raddr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "—",
                    "status": c.status,
                    "pid":    c.pid,
                })
        records.append({
            "timestamp":   now,
            "type":        "connections",
            "total":       len(conn_summary),
            "connections": conn_summary[:50],   # cap at 50
        })
    except (psutil.AccessDenied, Exception) as e:
        records.append({"timestamp": now, "type": "connections", "error": str(e)})

    # ── I/O delta ──
    try:
        net_io = psutil.net_io_counters(pernic=False)
        if _prev_net_io is not None:
            delta = {
                "timestamp":      now,
                "type":           "net_io_delta",
                "bytes_sent_sec": net_io.bytes_sent   - _prev_net_io.bytes_sent,
                "bytes_recv_sec": net_io.bytes_recv   - _prev_net_io.bytes_recv,
                "pkts_sent_sec":  net_io.packets_sent - _prev_net_io.packets_sent,
                "pkts_recv_sec":  net_io.packets_recv - _prev_net_io.packets_recv,
                "errin":          net_io.errin,
                "errout":         net_io.errout,
                "dropin":         net_io.dropin,
                "dropout":        net_io.dropout,
            }
            records.append(delta)
        _prev_net_io = net_io
    except Exception as e:
        records.append({"timestamp": now, "type": "net_io_delta", "error": str(e)})

    # ── Top network processes ──
    try:
        net_procs = []
        for proc in psutil.process_iter(["pid", "name", "connections"]):
            try:
                conns = proc.info.get("connections") or []
                active = [c for c in conns if c.status == "ESTABLISHED"]
                if active:
                    net_procs.append({
                        "pid":  proc.info["pid"],
                        "name": proc.info["name"],
                        "established_connections": len(active),
                    })
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
        records.append({
            "timestamp":       now,
            "type":            "net_processes",
            "processes":       sorted(net_procs, key=lambda x: x["established_connections"], reverse=True)[:10],
        })
    except Exception as e:
        records.append({"timestamp": now, "type": "net_processes", "error": str(e)})

    return records


# ─── Log Writer ───────────────────────────────────────────────────────────────

def append_jsonl(path: Path, records: list[dict]):
    """Append records to a .jsonl file (one JSON object per line)."""
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def read_recent_jsonl(path: Path, n: int = 100) -> list[dict]:
    """Read the last N records from a .jsonl file."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines[-n:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


# ─── Background Worker ────────────────────────────────────────────────────────

class SecurityMonitor:
    """
    Runs network + DLL + drive monitoring in background threads.
    Data is stored to log files; FastAPI reads from those files.
    """

    def __init__(
        self,
        net_interval:   int = 10,    # seconds between network snapshots
        dll_interval:   int = 120,   # seconds between DLL scans
        drive_interval: int = 180,   # seconds between drive scans
    ):
        self.net_interval   = net_interval
        self.dll_interval   = dll_interval
        self.drive_interval = drive_interval
        self._stop_evt      = threading.Event()

    def start(self):
        """Start background monitoring threads."""
        log.info("Security Monitor starting…")
        log.info("  Network snapshot every %ds", self.net_interval)
        log.info("  DLL entropy scan every %ds",  self.dll_interval)
        log.info("  Drive entropy scan every %ds", self.drive_interval)

        threading.Thread(target=self._net_loop,   daemon=True, name="NetMonitor").start()
        threading.Thread(target=self._dll_loop,   daemon=True, name="DllMonitor").start()
        threading.Thread(target=self._drive_loop, daemon=True, name="DriveMonitor").start()

    def stop(self):
        self._stop_evt.set()
        log.info("Security Monitor stopped.")

    def _net_loop(self):
        while not self._stop_evt.is_set():
            try:
                records = snapshot_network()
                append_jsonl(NET_LOG, records)
                log.info(
                    "[NET] %d records logged | connections: %s",
                    len(records),
                    next((r.get("total") for r in records if r["type"] == "connections"), "?"),
                )
            except Exception as e:
                log.error("[NET] Error: %s", e)
            self._stop_evt.wait(self.net_interval)

    def _dll_loop(self):
        self._stop_evt.wait(5)
        while not self._stop_evt.is_set():
            try:
                records = scan_dll_entropy()
                append_jsonl(DLL_LOG, records)
                suspicious = [r for r in records if r.get("suspicious")]
                log.info(
                    "[DLL] %d files scanned | %d suspicious",
                    len(records), len(suspicious),
                )
                if suspicious:
                    for s in suspicious:
                        log.warning("[DLL] ⚠ HIGH ENTROPY: %s (%.2f)", s["name"], s["entropy"])
            except Exception as e:
                log.error("[DLL] Error: %s", e)
            self._stop_evt.wait(self.dll_interval)

    def _drive_loop(self):
        self._stop_evt.wait(10)
        while not self._stop_evt.is_set():
            try:
                records = scan_drive_entropy()
                append_jsonl(DRIVE_LOG, records)
                suspicious = [r for r in records if r.get("suspicious")]
                log.info(
                    "[DRIVE] %d files sampled | %d suspicious",
                    len(records), len(suspicious),
                )
                if suspicious:
                    for s in suspicious:
                        log.warning("[DRIVE] ⚠ HIGH ENTROPY: %s (%.2f)", s["name"], s["entropy"])
            except Exception as e:
                log.error("[DRIVE] Error: %s", e)
            self._stop_evt.wait(self.drive_interval)


# Allow running standalone for testing
if __name__ == "__main__":
    import signal
    mon = SecurityMonitor(net_interval=10, dll_interval=60)
    mon.start()

    def _stop(sig, frame):
        mon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    log.info("Monitor running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
