"""
Quant Nexus: Cross-Cluster Heartbeat Emitter
Binds to 0.0.0.0 on port 8088.
Streams live MT5 metrics and daemon health to authorized peer nodes.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime, timezone
import MetaTrader5 as mt5

PORT = 8088

class HeartbeatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            metrics = self._gather_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(metrics, indent=2).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def _gather_metrics(self):
        mt5_ready = mt5.initialize(r"C:\Program Files\MetaTrader 5\terminal64.exe")
        account_data = {}
        positions_data = []

        if mt5_ready:
            acc = mt5.account_info()
            if acc:
                account_data = {
                    "balance": round(acc.balance, 2),
                    "equity": round(acc.equity, 2),
                    "margin": round(acc.margin, 2),
                    "free_margin": round(acc.margin_free, 2)
                }
            pos = mt5.positions_get()
            if pos:
                for p in pos:
                    positions_data.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": "BUY" if p.type == 0 else "SELL",
                        "volume": p.volume,
                        "profit": round(p.profit, 2)
                    })

        return {
            "cluster_node": "VPS-Golden-Master",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mt5_connected": bool(mt5_ready),
            "account": account_data,
            "open_positions_count": len(positions_data),
            "positions": positions_data
        }

    def log_message(self, format, *args):
        return

def run_server():
    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, HeartbeatHandler)
    print(f"[+] Heartbeat Emitter active on port {PORT}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        mt5.shutdown()

if __name__ == "__main__":
    run_server()