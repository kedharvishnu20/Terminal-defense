"""
main.py — FastAPI Security Monitor API
=======================================
Endpoints:
  GET  /api/logs/network         — Recent network log entries
  GET  /api/logs/dll             — Recent DLL entropy entries
  GET  /api/logs/drive           — Recent drive entropy entries
  GET  /api/logs/lockguard       — Recent system_lock guard logs
  GET  /api/logs/summary         — Quick stats for the dashboard
  POST /api/analyze              — Send logs to Meta AI and get analysis
  GET  /api/logs/ai              — Previous AI analysis logs
  WS   /ws/logs                  — WebSocket for live log streaming

  GET  /                         — Web dashboard (static/index.html)
"""

import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from monitor import (
    SecurityMonitor,
    NET_LOG,
    DLL_LOG,
    DRIVE_LOG,
    LOG_DIR,
    read_recent_jsonl,
    read_lock_guard_log,
)

# ─── Config (thresholds) ─────────────────────────────────────────────────────

import pathlib

SEC_CONFIG_FILE = pathlib.Path(__file__).parent / "config.json"

def _load_sec_config() -> dict:
    """Load optional config for thresholds."""
    defaults = {
        "high_entropy_threshold": 7.2,
        "high_connection_threshold": 100,
    }
    if SEC_CONFIG_FILE.exists():
        try:
            with open(SEC_CONFIG_FILE, encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    else:
        with open(SEC_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=4)
    return defaults

SEC_CONFIG = _load_sec_config()

# ─── Logging ─────────────────────────────────────────────────────────────────

log = logging.getLogger("SecAPI")

# ─── Globals ─────────────────────────────────────────────────────────────────

monitor    = SecurityMonitor(net_interval=10, dll_interval=120, drive_interval=180)
_ws_clients: list[WebSocket] = []
_last_net_line   = 0
_last_dll_line   = 0
_last_drive_line = 0

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor.start()
    asyncio.create_task(broadcast_new_logs())
    log.info("FastAPI started — monitor running.")
    yield
    monitor.stop()
    log.info("FastAPI shutdown — monitor stopped.")

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Security Monitor API",
    description="Network · DLL Entropy · Drive Entropy · Lock Guard · Meta AI",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def serve_dashboard():
    html_file = STATIC_DIR / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


@app.get("/api/logs/network", tags=["Logs"])
async def get_network_logs(n: int = 100):
    records = read_recent_jsonl(NET_LOG, n)
    return {"count": len(records), "records": records}


@app.get("/api/logs/dll", tags=["Logs"])
async def get_dll_logs(n: int = 100):
    records = read_recent_jsonl(DLL_LOG, n)
    return {"count": len(records), "records": records}


@app.get("/api/logs/drive", tags=["Logs"])
async def get_drive_logs(n: int = 100):
    """Return the last N drive entropy entries."""
    records = read_recent_jsonl(DRIVE_LOG, n)
    return {"count": len(records), "records": records}


@app.get("/api/logs/lockguard", tags=["Logs"])
async def get_lock_guard_logs(n: int = 100):
    """Return the last N lines from system_lock/logs/lock_guard.log."""
    records = read_lock_guard_log(n)
    return {"count": len(records), "records": records}


@app.get("/api/logs/summary", tags=["Logs"])
async def get_summary():
    net_records   = read_recent_jsonl(NET_LOG, 200)
    dll_records   = read_recent_jsonl(DLL_LOG, 200)
    drive_records = read_recent_jsonl(DRIVE_LOG, 200)

    # Network
    conn_records = [r for r in net_records if r.get("type") == "connections"]
    latest_conns = conn_records[-1].get("total", 0) if conn_records else 0
    io_records   = [r for r in net_records if r.get("type") == "net_io_delta"]
    latest_io    = io_records[-1] if io_records else {}

    # DLL
    dll_ent      = [r for r in dll_records if r.get("type") == "dll_entropy"]
    dll_susp     = [r for r in dll_ent if r.get("suspicious")]
    dll_avg      = (
        round(sum(r["entropy"] for r in dll_ent) / max(len(dll_ent), 1), 3)
        if dll_ent else 0
    )

    # Drive
    drv_ent      = [r for r in drive_records if r.get("type") == "drive_entropy"]
    drv_susp     = [r for r in drv_ent if r.get("suspicious")]
    drv_avg      = (
        round(sum(r["entropy"] for r in drv_ent) / max(len(drv_ent), 1), 3)
        if drv_ent else 0
    )

    # Lock Guard
    lg_logs = read_lock_guard_log(50)
    lg_warnings = len([l for l in lg_logs if l.get("level") in ("WARNING", "ERROR", "CRITICAL")])

    return {
        "network": {
            "active_connections":   latest_conns,
            "bytes_sent_per_sec":   latest_io.get("bytes_sent_sec", 0),
            "bytes_recv_per_sec":   latest_io.get("bytes_recv_sec", 0),
            "packets_sent_per_sec": latest_io.get("pkts_sent_sec", 0),
            "packets_recv_per_sec": latest_io.get("pkts_recv_sec", 0),
            "errors_in":            latest_io.get("errin", 0),
            "errors_out":           latest_io.get("errout", 0),
        },
        "dll": {
            "total_scanned":    len(dll_ent),
            "suspicious_count": len(dll_susp),
            "average_entropy":  dll_avg,
        },
        "drive": {
            "total_sampled":    len(drv_ent),
            "suspicious_count": len(drv_susp),
            "average_entropy":  drv_avg,
        },
        "lockguard": {
            "total_entries": len(lg_logs),
            "warnings":     lg_warnings,
        },
    }


# ─── Local Rule-Based Analyzer (fallback) ─────────────────────────────────────

def _local_analysis(log_summary: str) -> str:
    """
    Produce a rule-based security analysis without any external AI.
    Parses live log data and returns a structured, human-readable report.
    """
    from datetime import datetime

    findings_net  = []
    findings_dll  = []
    findings_drv  = []
    findings_lg   = []
    risk_level    = "LOW"

    # ── Gather data ──
    net_recs = read_recent_jsonl(NET_LOG, 50)
    dll_recs = read_recent_jsonl(DLL_LOG, 100)
    drv_recs = read_recent_jsonl(DRIVE_LOG, 100)
    lg_recs  = read_lock_guard_log(50)

    h_conn = SEC_CONFIG.get("high_connection_threshold", 100)
    h_ent  = SEC_CONFIG.get("high_entropy_threshold", 7.2)

    def _fmt_bytes(b):
        if b >= 1e9:  return f"{b/1e9:.1f} GB/s"
        if b >= 1e6:  return f"{b/1e6:.1f} MB/s"
        if b >= 1e3:  return f"{b/1e3:.1f} KB/s"
        return f"{b} B/s"

    # ────────────────────────────────────────────────
    #  1) NETWORK
    # ────────────────────────────────────────────────
    conn_rec    = next((r for r in reversed(net_recs) if r.get("type") == "connections"), {})
    total_conns = conn_rec.get("total", 0)

    if total_conns > h_conn:
        findings_net.append(f"  ⚠  Active Connections  : {total_conns}  (threshold: {h_conn})")
        findings_net.append(f"     → Elevated — may indicate port scan, DDoS, or C2 beaconing")
        if risk_level == "LOW":
            risk_level = "MEDIUM"
    elif total_conns > 0:
        findings_net.append(f"  ✅  Active Connections  : {total_conns}  (normal)")

    io_rec = next((r for r in reversed(net_recs) if r.get("type") == "net_io_delta"), {})
    recv = io_rec.get("bytes_recv_sec", 0)
    sent = io_rec.get("bytes_sent_sec", 0)

    findings_net.append(f"  📥  Ingress Rate       : {_fmt_bytes(recv)}")
    findings_net.append(f"  📤  Egress Rate        : {_fmt_bytes(sent)}")

    if recv > 50_000_000:
        findings_net.append(f"      → ⚠ VERY HIGH ingress — possible data flood")
        risk_level = "HIGH"
    if sent > 10_000_000:
        findings_net.append(f"      → ⚠ HIGH egress — possible data exfiltration")
        risk_level = "HIGH"

    err_in  = io_rec.get("errin", 0)
    err_out = io_rec.get("errout", 0)
    if err_in or err_out:
        findings_net.append(f"  ❌  Network Errors      : IN={err_in}  OUT={err_out}")

    proc_rec  = next((r for r in reversed(net_recs) if r.get("type") == "net_processes"), {})
    top_procs = proc_rec.get("processes", [])
    suspect_names = ["nc.exe", "ncat", "mimikatz", "meterpreter",
                     "reverse", "powershell_ise", "psexec", "cobaltstrike"]
    heavy = [(p["name"], p["pid"], p["established_connections"])
             for p in top_procs[:5] if p.get("established_connections", 0) > 20]
    if heavy:
        findings_net.append("")
        findings_net.append("  Top Processes (>20 connections):")
        for name, pid, c in heavy:
            findings_net.append(f"    │ {name:<22s} PID {pid:<6}  {c} conn")

    for p in top_procs[:5]:
        if any(s in p.get("name", "").lower() for s in suspect_names):
            findings_net.append(f"  🚨  ALERT: '{p['name']}' (PID {p['pid']}) — known attack tool!")
            risk_level = "CRITICAL"

    # ────────────────────────────────────────────────
    #  2) DLL ENTROPY
    # ────────────────────────────────────────────────
    dll_all  = [r for r in dll_recs if r.get("type") == "dll_entropy"]
    dll_susp = [r for r in dll_recs if r.get("suspicious")]

    findings_dll.append(f"  📁  Total Scanned      : {len(dll_all)}")
    findings_dll.append(f"  ⚠   Suspicious (≥{h_ent}) : {len(dll_susp)}")

    if dll_susp:
        findings_dll.append("")
        findings_dll.append("  Flagged DLLs:")
        for s in dll_susp[:8]:
            pct = int(s["entropy"] / 8 * 20)
            bar = "█" * pct + "░" * (20 - pct)
            findings_dll.append(f"    │ {s['name']:<32s} {s['entropy']:.3f}  [{bar}]")
        if risk_level == "LOW":
            risk_level = "MEDIUM"
    else:
        findings_dll.append("  ✅  All DLLs have normal entropy — no packing detected")

    # ────────────────────────────────────────────────
    #  3) DRIVE ENTROPY
    # ────────────────────────────────────────────────
    drv_all  = [r for r in drv_recs if r.get("type") == "drive_entropy"]
    drv_susp = [r for r in drv_recs if r.get("suspicious")]

    findings_drv.append(f"  📁  Files Sampled      : {len(drv_all)}")
    findings_drv.append(f"  ⚠   Suspicious (≥{h_ent}) : {len(drv_susp)}")

    if drv_susp:
        findings_drv.append("")
        findings_drv.append("  Flagged Files:")
        for s in drv_susp[:8]:
            drive = s.get("drive", "?")
            pct = int(s["entropy"] / 8 * 20)
            bar = "█" * pct + "░" * (20 - pct)
            findings_drv.append(f"    │ {s['name']:<28s} [{drive}]  {s['entropy']:.3f}  [{bar}]")
        if risk_level == "LOW":
            risk_level = "MEDIUM"
    else:
        findings_drv.append("  ✅  All sampled files have normal entropy")

    # ────────────────────────────────────────────────
    #  4) LOCK GUARD
    # ────────────────────────────────────────────────
    lg_warns = [r for r in lg_recs if r.get("level") in ("WARNING", "ERROR", "CRITICAL")]

    findings_lg.append(f"  📋  Total Entries      : {len(lg_recs)}")
    findings_lg.append(f"  ⚠   Warnings/Errors   : {len(lg_warns)}")

    if lg_warns:
        findings_lg.append("")
        for w in lg_warns[-5:]:
            icon = "🚨" if w["level"] == "CRITICAL" else "⚠ "
            findings_lg.append(f"  {icon} [{w['level']}] {w.get('timestamp', '')}")
            findings_lg.append(f"     {w.get('message', '')}")
    else:
        findings_lg.append("  ✅  No warnings or errors — system lock is healthy")

    # ═══════════════════════ BUILD REPORT ═══════════════════════
    risk_icons = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    r = []
    r.append("┌──────────────────────────────────────────────────────────────┐")
    r.append("│               SECURITY ANALYSIS REPORT                      │")
    r.append("│               Local Rule-Based Engine                       │")
    r.append("└──────────────────────────────────────────────────────────────┘")
    r.append("")
    r.append(f"  📅 Timestamp   : {now}")
    r.append(f"  {risk_icons.get(risk_level, '⚪')}  Risk Level  : {risk_level}")
    r.append(f"  📊 Data Scope  : {len(net_recs)} network · {len(dll_all)} DLLs"
             f" · {len(drv_all)} drive files · {len(lg_recs)} lock guard")
    r.append("")

    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.append("  📡  SECTION 1 — NETWORK ACTIVITY")
    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.extend(findings_net)
    r.append("")

    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.append("  🔬  SECTION 2 — DLL ENTROPY SCAN")
    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.extend(findings_dll)
    r.append("")

    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.append("  💽  SECTION 3 — DRIVE ENTROPY SCAN")
    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.extend(findings_drv)
    r.append("")

    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.append("  🔒  SECTION 4 — LOCK GUARD STATUS")
    r.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r.extend(findings_lg)
    r.append("")

    r.append("┌──────────────────────────────────────────────────────────────┐")
    r.append("│  📋  RECOMMENDATIONS                                        │")
    r.append("└──────────────────────────────────────────────────────────────┘")
    r.append("")

    if risk_level == "CRITICAL":
        r.append("  🚨 IMMEDIATE ACTION REQUIRED:")
        r.append("     1. Disconnect from the network immediately")
        r.append("     2. Terminate the suspicious processes listed above")
        r.append("     3. Run a full antivirus & anti-malware scan")
        r.append("     4. Preserve logs for forensic investigation")
        r.append("     5. Notify your security team / administrator")
    elif risk_level == "HIGH":
        r.append("  ⚠  URGENT — Take action soon:")
        r.append("     1. Investigate high-entropy files — may be ransomware")
        r.append("     2. Monitor egress traffic for exfiltration patterns")
        r.append("     3. Review processes making unauthorized connections")
        r.append("     4. Run a targeted scan on flagged files")
    elif risk_level == "MEDIUM":
        r.append("  🟡 MODERATE — Review recommended:")
        r.append("     1. Manually inspect the flagged high-entropy files")
        r.append("     2. Verify all connections are from trusted applications")
        r.append("     3. Run a quick malware scan as a precaution")
        r.append("     4. Check if connection count is typical for your usage")
    else:
        r.append("  🟢 ALL CLEAR — No anomalies detected:")
        r.append("     1. All scanned areas are within normal parameters")
        r.append("     2. Continue routine monitoring")
        r.append("     3. Tip: Schedule deeper scans during off-peak hours")

    r.append("")
    r.append("──────────────────────────────────────────────────────────────")
    r.append(f"  Generated: {now}  •  Engine: Local Rule-Based Analyzer v1.0")
    r.append("──────────────────────────────────────────────────────────────")

    return "\n".join(r)


@app.post("/api/analyze", tags=["AI"])
async def analyze_with_ai(request: dict):
    include_net   = request.get("include_network", True)
    include_dll   = request.get("include_dll", True)
    include_drive = request.get("include_drive", True)
    include_lg    = request.get("include_lockguard", False)
    n             = request.get("n_records", 20)
    context       = request.get("context", "")

    sections = []

    if include_net:
        net_recs = read_recent_jsonl(NET_LOG, n)
        conn  = next((r for r in reversed(net_recs) if r.get("type") == "connections"), {})
        io    = next((r for r in reversed(net_recs) if r.get("type") == "net_io_delta"), {})
        procs = next((r for r in reversed(net_recs) if r.get("type") == "net_processes"), {})
        sections.append(
            f"=== NETWORK ===\n"
            f"Active connections: {conn.get('total','N/A')}\n"
            f"Bytes sent/s: {io.get('bytes_sent_sec','N/A')} | Bytes recv/s: {io.get('bytes_recv_sec','N/A')}\n"
            f"Top processes: {json.dumps(procs.get('processes',[])[:5], indent=2)}\n"
        )

    if include_dll:
        dll_recs   = read_recent_jsonl(DLL_LOG, n)
        suspicious = [r for r in dll_recs if r.get("suspicious")]
        avg = sum(r["entropy"] for r in dll_recs if "entropy" in r) / max(len(dll_recs), 1)
        sections.append(
            f"=== DLL ENTROPY ===\n"
            f"Files scanned: {len(dll_recs)} | Avg entropy: {avg:.3f}\n"
            f"Suspicious (≥7.2): {len(suspicious)}\n"
            + ("".join(f"  - {r['name']}: {r['entropy']:.3f}\n" for r in suspicious[:10])
               if suspicious else "No suspicious DLLs.\n")
        )

    if include_drive:
        drv_recs   = read_recent_jsonl(DRIVE_LOG, n)
        drv_susp   = [r for r in drv_recs if r.get("suspicious")]
        drv_avg    = sum(r["entropy"] for r in drv_recs if "entropy" in r) / max(len(drv_recs), 1)
        sections.append(
            f"=== DRIVE ENTROPY ===\n"
            f"Files sampled: {len(drv_recs)} | Avg entropy: {drv_avg:.3f}\n"
            f"Suspicious: {len(drv_susp)}\n"
            + ("".join(f"  - {r['name']} ({r.get('drive','')}): {r['entropy']:.3f}\n" for r in drv_susp[:10])
               if drv_susp else "No suspicious drive files.\n")
        )

    if include_lg:
        lg_recs = read_lock_guard_log(30)
        if lg_recs:
            sections.append(
                f"=== LOCK GUARD LOGS ===\n"
                + "".join(f"  [{r['level']}] {r['timestamp']} {r['message']}\n" for r in lg_recs[-15:])
            )

    log_summary = "\n\n".join(sections)
    user_question = context or (
        "Analyze these system security logs. "
        "Identify any anomalies, suspicious activity, or potential threats. "
        "Give a concise security assessment."
    )

    prompt = (
        f"You are a cybersecurity analyst. "
        f"Here are real-time system security logs:\n\n"
        f"{log_summary}\n\n"
        f"Question: {user_question}\n\n"
        f"Please provide a clear security analysis."
    )

    import time as _time

    ai_message = None
    sources    = []

    try:
        from meta_ai_api import MetaAI
        last_err = None
        for attempt in range(3):
            try:
                ai = MetaAI()
                response = ai.prompt(message=prompt)
                ai_message = response.get("message", "No response received.")
                sources    = response.get("sources", [])
                break   # success
            except Exception as e:
                last_err = e
                log.warning("Meta AI attempt %d/3 failed: %s", attempt + 1, e)
                if attempt < 2:
                    _time.sleep(2)   # wait before retry
        if ai_message is None:
            log.warning("All Meta AI attempts failed — using local analysis.")
            ai_message = _local_analysis(log_summary)
    except ImportError:
        log.warning("meta-ai-api not installed — using local analysis.")
        ai_message = _local_analysis(log_summary)

    ai_log_path = LOG_DIR / "ai_analysis_log.jsonl"
    with open(ai_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp":  __import__("datetime").datetime.now().isoformat(),
            "prompt":     prompt[:500] + "..." if len(prompt) > 500 else prompt,
            "response":   ai_message,
            "sources":    sources,
        }) + "\n")

    return {
        "analysis":    ai_message,
        "sources":     sources,
        "log_summary": log_summary,
    }


@app.get("/api/logs/ai", tags=["AI"])
async def get_ai_logs(n: int = 20):
    ai_log = LOG_DIR / "ai_analysis_log.jsonl"
    return {"records": read_recent_jsonl(ai_log, n)}


# ─── WebSocket – Live Log Stream ─────────────────────────────────────────────

@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    log.info("WS client connected. Total: %d", len(_ws_clients))
    try:
        while True:
            await asyncio.sleep(5)
            await ws.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, RuntimeError):
        pass   # client disconnected — silently clean up
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)
        log.info("WS client disconnected. Total: %d", len(_ws_clients))


async def broadcast_new_logs():
    global _last_net_line, _last_dll_line, _last_drive_line
    while True:
        await asyncio.sleep(5)
        new_entries = []

        for log_file, source, last_attr in [
            (NET_LOG,   "network", "_last_net_line"),
            (DLL_LOG,   "dll",     "_last_dll_line"),
            (DRIVE_LOG, "drive",   "_last_drive_line"),
        ]:
            if log_file.exists():
                lines = log_file.read_text(encoding="utf-8").strip().splitlines()
                last_val = globals()[last_attr]
                for line in lines[last_val:]:
                    try:
                        new_entries.append({"source": source, "data": json.loads(line)})
                    except Exception:
                        pass
                globals()[last_attr] = len(lines)

        if new_entries and _ws_clients:
            payload = json.dumps({"type": "logs", "entries": new_entries})
            dead = []
            for client in _ws_clients:
                try:
                    await client.send_text(payload)
                except Exception:
                    dead.append(client)
            for d in dead:
                _ws_clients.remove(d)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
