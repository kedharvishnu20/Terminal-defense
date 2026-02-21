# 📡 Security Monitor

Real-time security scanner with a web dashboard — monitors network connections, DLL entropy, drive file entropy, and system lock guard status. Includes AI-powered analysis via Meta AI with automatic fallback to a local rule-based engine.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🌐 **Network Monitoring** | Tracks active connections, bandwidth, process-level traffic, suspicious tools |
| 🔬 **DLL Entropy Scan** | Detects packed/encoded DLLs via Shannon entropy analysis |
| 💽 **Drive Entropy Scan** | Random sampling of files across all drives to detect ransomware |
| 🔒 **Lock Guard Integration** | Reads and analyzes system lock guard logs |
| 🤖 **AI Analysis** | Meta AI integration with retry logic and local fallback |
| 📊 **Web Dashboard** | Real-time dashboard at `http://localhost:8000` |
| 🔄 **Live Updates** | WebSocket streaming for real-time log updates |

## 🚀 Quick Start

```bash
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Or use the unified launcher from the project root:
```batch
start.bat     →   Option [1]
```

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web dashboard |
| `GET` | `/api/logs/network` | Recent network log entries |
| `GET` | `/api/logs/dll` | Recent DLL entropy entries |
| `GET` | `/api/logs/drive` | Recent drive entropy entries |
| `GET` | `/api/logs/lockguard` | Recent Lock Guard log entries |
| `GET` | `/api/logs/summary` | Quick stats for the dashboard |
| `POST` | `/api/analyze` | Trigger AI / local analysis |
| `GET` | `/api/logs/ai` | Previous AI analysis results |
| `WS` | `/ws/logs` | WebSocket for live log streaming |

## ⚙️ Configuration

Edit `config.json`:

```json
{
    "high_entropy_threshold": 7.2,
    "high_connection_threshold": 100
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `high_entropy_threshold` | `7.2` | Shannon entropy above this is flagged as suspicious |
| `high_connection_threshold` | `100` | Connection count above this triggers warnings |

## 📁 Files

```
├── main.py              # FastAPI server, API routes, AI analysis
├── monitor.py           # Background scanner (network, DLL, drive entropy)
├── config.json          # Detection thresholds
├── requirements.txt     # Python dependencies
├── run_server.bat       # Standalone Windows launcher
├── static/
│   └── index.html       # Web dashboard UI
└── logs/                # Generated at runtime
    ├── network_log.jsonl
    ├── dll_entropy_log.jsonl
    ├── drive_entropy_log.jsonl
    └── ai_analysis_log.jsonl
```

## 📋 Analysis Report

The analysis engine produces structured reports with:
- Color-coded risk levels (🟢 LOW / 🟡 MEDIUM / 🟠 HIGH / 🔴 CRITICAL)
- Separate sections for Network, DLL, Drive, and Lock Guard findings
- Visual entropy bars for flagged files
- Actionable recommendations based on risk level
