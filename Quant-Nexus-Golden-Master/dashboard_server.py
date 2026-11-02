import os
import sys
import sqlite3
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

load_dotenv(override=True)
DB_PATH = os.path.join(BASE_DIR, "quant_metrics.db")

app = FastAPI(title="Quant Nexus - Institutional Terminal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Quant Nexus | Institutional Terminal</title>
    <style>
        body { background-color: #0b0e14; color: #d1d5db; font-family: monospace; padding: 24px; margin: 0; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; padding-bottom: 16px; margin-bottom: 24px; }
        .badge { background: #8b5cf6; color: #fff; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card { background: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 18px; }
        .val { font-size: 24px; font-weight: bold; color: #10b981; margin-top: 6px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #1f2937; font-size: 13px; }
        th { color: #9ca3af; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h2 style="margin:0; color:#f9fafb;">⚡ QUANT NEXUS TERMINAL</h2>
            <small style="color:#6b7280;">Shivsoul Moat Operational Telemetry</small>
        </div>
        <div>
            <span class="badge">ELITE OPERATOR</span>
            <span style="margin-left: 8px; color:#9ca3af;">@Shivsoul</span>
        </div>
    </div>
    <div class="grid">
        <div class="card">
            <small style="color:#9ca3af;">REGIME STATE</small>
            <div class="val">ACTIVE_OPTIMAL</div>
        </div>
        <div class="card">
            <small style="color:#9ca3af;">SPREAD GATE</small>
            <div class="val" style="color:#10b981;">GUARD_ENABLED</div>
        </div>
        <div class="card">
            <small style="color:#9ca3af;">COMMUNITY CONVICTION</small>
            <div class="val" style="color:#6366f1;">REPUTATION_WEIGHTED</div>
        </div>
    </div>
    <div class="card">
        <h3 style="margin-top:0; color:#f9fafb;">Audit Trail</h3>
        <table>
            <thead>
                <tr>
                    <th>Signal ID</th>
                    <th>Asset</th>
                    <th>Action</th>
                    <th>Entry</th>
                    <th>Upvotes</th>
                    <th>Downvotes</th>
                    <th>Outcome</th>
                </tr>
            </thead>
            <tbody id="rows">
                <tr><td colspan="7" style="text-align:center;">Loading signals...</td></tr>
            </tbody>
        </table>
    </div>
    <script>
        async function fetchFeed() {
            try {
                const res = await fetch('/api/v1/telemetry/signals');
                const data = await res.json();
                const tbody = document.getElementById('rows');
                tbody.innerHTML = '';
                data.forEach(s => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><code>${s.signal_id}</code></td>
                        <td><strong>${s.asset}</strong> (${s.timeframe})</td>
                        <td style="color:${s.direction === 'BUY' ? '#10b981' : '#ef4444'}">${s.direction}</td>
                        <td>${s.entry_price.toFixed(2)}</td>
                        <td>👍 ${s.upvotes}</td>
                        <td>👎 ${s.downvotes}</td>
                        <td><strong>${s.outcome}</strong></td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch(e) { console.error(e); }
        }
        fetchFeed();
        setInterval(fetchFeed, 5000);
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_CONTENT

@app.get("/api/v1/telemetry/signals")
def get_signals():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_telemetry (
            signal_id TEXT PRIMARY KEY,
            asset TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            signature TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            outcome TEXT DEFAULT 'PENDING'
        )
    """)
    cursor.execute("""
        SELECT signal_id, asset, timeframe, direction, entry_price, upvotes, downvotes, outcome
        FROM signal_telemetry
        ORDER BY rowid DESC
        LIMIT 25
    """)
    records = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return records
