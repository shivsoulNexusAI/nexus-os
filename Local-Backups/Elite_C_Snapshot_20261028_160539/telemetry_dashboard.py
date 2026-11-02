import os
import json
import subprocess
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import MetaTrader5 as mt5

app = FastAPI(title="Quant Nexus Telemetry")

LOGIN = 278017866
PASSWORD = "H@ngkook3695"
SERVER = "Exness-MT5Trial5"
CB_STATE_PATH = r"C:\Quant-Nexus-Eng\Quant-Nexus-Golden-Master\circuit_breaker_state.json"

def get_engine_processes():
    engines = {
        "watchdog": {"name": "Watchdog Supervisor", "running": False, "pid": None},
        "daemon": {"name": "Quantum Delta Daemon", "running": False, "pid": None},
        "deal_watcher": {"name": "Deal Resolution Watcher", "running": False, "pid": None},
        "breakeven": {"name": "Breakeven Engine", "running": False, "pid": None}
    }
    
    # Query Win32_Process using PowerShell to bypass cross-session permission boundaries
    ps_cmd = 'Get-CimInstance Win32_Process | Select-Object ProcessId, CommandLine | ConvertTo-Json -Compress'
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=4)
        if res.returncode == 0 and res.stdout.strip():
            raw = json.loads(res.stdout)
            procs = raw if isinstance(raw, list) else [raw]
            for p in procs:
                cmd = p.get("CommandLine") or ""
                pid = p.get("ProcessId")
                if "watchdog_daemon.ps1" in cmd:
                    engines["watchdog"] = {"name": "Watchdog Supervisor", "running": True, "pid": pid}
                elif "quantum_delta_daemon.py" in cmd:
                    engines["daemon"] = {"name": "Quantum Delta Daemon", "running": True, "pid": pid}
                elif "deal_resolution_watcher.py" in cmd:
                    engines["deal_watcher"] = {"name": "Deal Resolution Watcher", "running": True, "pid": pid}
                elif "breakeven_engine.py" in cmd:
                    engines["breakeven"] = {"name": "Breakeven Engine", "running": True, "pid": pid}
    except Exception:
        pass
            
    return engines

@app.get("/api/telemetry")
def get_telemetry():
    engines = get_engine_processes()

    hwm, floor, is_tripped = 0.0, 0.0, False
    if os.path.exists(CB_STATE_PATH):
        try:
            with open(CB_STATE_PATH, "r", encoding="utf-8") as f:
                cb = json.load(f)
                hwm = cb.get("high_water_mark", 0.0)
                floor = cb.get("current_floor", 0.0)
                is_tripped = cb.get("is_tripped", False)
        except Exception:
            pass

    account_data = {"balance": 0.0, "equity": 0.0, "margin_level": 0.0, "free_margin": 0.0}
    positions_data = []

    connected = mt5.initialize() and mt5.login(login=LOGIN, password=PASSWORD, server=SERVER)
    if connected:
        acc = mt5.account_info()
        if acc:
            account_data = {
                "balance": acc.balance,
                "equity": acc.equity,
                "margin_level": acc.margin_level,
                "free_margin": acc.margin_free
            }
        positions = mt5.positions_get()
        if positions:
            for p in positions:
                is_buy = (p.type == mt5.ORDER_TYPE_BUY)
                risk = abs(p.price_open - p.sl) if p.sl > 0 else 0.0001
                gain = (p.price_current - p.price_open) if is_buy else (p.price_open - p.price_current)
                r_mult = gain / risk if risk > 0 else 0.0
                be = (is_buy and p.sl >= p.price_open) or (not is_buy and p.sl <= p.price_open and p.sl != 0.0)
                
                positions_data.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "side": "BUY" if is_buy else "SELL",
                    "volume": p.volume,
                    "open": p.price_open,
                    "mark": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "r_mult": round(r_mult, 2),
                    "be_locked": be
                })
        mt5.shutdown()

    buffer_val = account_data["equity"] - floor if account_data["equity"] > 0 else 0.0

    return {
        "account": account_data,
        "circuit_breaker": {
            "hwm": hwm,
            "floor": floor,
            "buffer": buffer_val,
            "is_tripped": is_tripped
        },
        "engines": engines,
        "positions": positions_data
    }

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Quantum Nexus // Operations Terminal</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
        body { background: #0d1117; color: #c9d1d9; padding: 24px; }
        h1 { font-size: 20px; font-weight: 600; color: #58a6ff; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
        .card-label { font-size: 12px; color: #8b949e; text-transform: uppercase; margin-bottom: 6px; }
        .card-value { font-size: 24px; font-weight: 700; color: #f0f6fc; }
        .card-sub { font-size: 12px; margin-top: 4px; color: #8b949e; }
        .status-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 3px 8px; border-radius: 12px; }
        .status-online { background: rgba(46, 160, 67, 0.15); color: #3fb950; border: 1px solid rgba(46, 160, 67, 0.4); }
        .status-offline { background: rgba(248, 81, 73, 0.15); color: #f85149; border: 1px solid rgba(248, 81, 73, 0.4); }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #21262d; }
        th { color: #8b949e; font-weight: 600; background: #161b22; }
        tr:hover { background: #1c2128; }
        .pnl-pos { color: #3fb950; font-weight: 600; }
        .pnl-neg { color: #f85149; font-weight: 600; }
        .pulse { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; display: inline-block; animation: blink 1.5s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
    </style>
</head>
<body>
    <h1><span class="pulse"></span> QUANTUM NEXUS // SHIP SOUL TELEMETRY</h1>

    <div class="grid">
        <div class="card">
            <div class="card-label">Account Equity</div>
            <div class="card-value" id="val-equity">$0.00</div>
            <div class="card-sub" id="val-balance">Balance: $0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Circuit Breaker Floor</div>
            <div class="card-value" id="val-floor">$0.00</div>
            <div class="card-sub" id="val-buffer">Buffer: +$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Margin Level</div>
            <div class="card-value" id="val-margin">0.0%</div>
            <div class="card-sub" id="val-freemargin">Free: $0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Defensive Architecture</div>
            <div class="card-value" style="font-size: 16px; margin-top: 6px;" id="val-engines-count">0 / 4 Engines Active</div>
            <div class="card-sub" id="val-cb-status">Circuit Status: ARMED</div>
        </div>
    </div>

    <div class="card" style="margin-bottom: 24px;">
        <div class="card-label">Process Execution Stack</div>
        <div id="engines-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 10px;"></div>
    </div>

    <div class="card">
        <div class="card-label">Live Active Positions</div>
        <table id="pos-table">
            <thead>
                <tr>
                    <th>Ticket</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Volume</th>
                    <th>Open Price</th>
                    <th>Mark Price</th>
                    <th>Stop Loss</th>
                    <th>R-Multiple</th>
                    <th>Floating PnL</th>
                    <th>Defense</th>
                </tr>
            </thead>
            <tbody id="pos-body">
                <tr><td colspan="10" style="text-align: center; color: #8b949e;">No open positions. Flat exposure.</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        async function updateDashboard() {
            try {
                const res = await fetch('/api/telemetry');
                const data = await res.json();

                document.getElementById('val-equity').innerText = '$' + data.account.equity.toFixed(2);
                document.getElementById('val-balance').innerText = 'Balance: $' + data.account.balance.toFixed(2);
                document.getElementById('val-margin').innerText = data.account.margin_level.toFixed(1) + '%';
                document.getElementById('val-freemargin').innerText = 'Free: $' + data.account.free_margin.toFixed(2);

                document.getElementById('val-floor').innerText = '$' + data.circuit_breaker.floor.toFixed(2);
                document.getElementById('val-buffer').innerText = 'Buffer: +$' + data.circuit_breaker.buffer.toFixed(2) + ' (HWM: $' + data.circuit_breaker.hwm.toFixed(2) + ')';
                document.getElementById('val-cb-status').innerText = 'Circuit Status: ' + (data.circuit_breaker.is_tripped ? 'TRIPPED' : 'ARMED');

                const enginesGrid = document.getElementById('engines-grid');
                enginesGrid.innerHTML = '';
                let activeCount = 0;
                for (const [key, e] of Object.entries(data.engines)) {
                    if (e.running) activeCount++;
                    const badgeClass = e.running ? 'status-online' : 'status-offline';
                    const statusText = e.running ? `ONLINE (PID ${e.pid})` : 'OFFLINE';
                    enginesGrid.innerHTML += `
                        <div style="background: #0d1117; padding: 10px; border-radius: 6px; border: 1px solid #21262d;">
                            <div style="font-size: 11px; color: #8b949e;">${e.name}</div>
                            <div style="margin-top: 6px;"><span class="status-badge ${badgeClass}">${statusText}</span></div>
                        </div>
                    `;
                }
                document.getElementById('val-engines-count').innerText = `${activeCount} / 4 Engines Active`;

                const tbody = document.getElementById('pos-body');
                if (data.positions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #8b949e;">No open positions. Flat exposure.</td></tr>';
                } else {
                    tbody.innerHTML = '';
                    data.positions.forEach(p => {
                        const pnlClass = p.profit >= 0 ? 'pnl-pos' : 'pnl-neg';
                        const defenseTag = p.be_locked ? '<span class="status-badge status-online">🔒 BREAKEVEN</span>' : `<span style="color:#8b949e;">${p.r_mult >= 0 ? '+' : ''}${p.r_mult}R</span>`;
                        tbody.innerHTML += `
                            <tr>
                                <td>#${p.ticket}</td>
                                <td><strong>${p.symbol}</strong></td>
                                <td>${p.side}</td>
                                <td>${p.volume.toFixed(2)}L</td>
                                <td>${p.open.toFixed(5)}</td>
                                <td>${p.mark.toFixed(5)}</td>
                                <td>${p.sl > 0 ? p.sl.toFixed(5) : '-'}</td>
                                <td>${p.r_mult >= 0 ? '+' : ''}${p.r_mult}R</td>
                                <td class="${pnlClass}">${p.profit >= 0 ? '+' : ''}$${p.profit.toFixed(2)}</td>
                                <td>${defenseTag}</td>
                            </tr>
                        `;
                    });
                }
            } catch (err) {
                console.error("Telemetry fetch failed", err);
            }
        }
        setInterval(updateDashboard, 3000);
        updateDashboard();
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
