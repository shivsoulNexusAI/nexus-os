import os
import json
import time
import glob
from fastapi import FastAPI, Response
from prometheus_client import Counter, Gauge, REGISTRY, generate_latest, CONTENT_TYPE_LATEST
import uvicorn

app = FastAPI(title="QuantNexus Governor")

def get_or_create_gauge(name, documentation, labelnames=()):
    try:
        return Gauge(name, documentation, labelnames)
    except ValueError:
        return REGISTRY._names_to_collectors[name]

def get_or_create_counter(name, documentation, labelnames=()):
    try:
        return Counter(name, documentation, labelnames)
    except ValueError:
        return REGISTRY._names_to_collectors[name]

FLEET_NAV_GAUGE = get_or_create_gauge('quant_fleet_nav_dollars', 'Current NAV per sleeve', ['sleeve'])
FLEET_DD_PCT_GAUGE = get_or_create_gauge('quant_fleet_drawdown_pct', 'Weekly drawdown percentage vs $3,000 anchor')
BACKUP_AGE_HOURS_GAUGE = get_or_create_gauge('quant_backup_age_hours', 'Hours since last successful local backup ZIP')
TRADE_COUNTER = get_or_create_counter('quant_trades_total', 'Total executed trades', ['sleeve', 'symbol'])

def refresh_operational_metrics():
    # 1. Check latest backup age in C:\Quant-Nexus-Backups
    zips = glob.glob(r"C:\Quant-Nexus-Backups\QuantNexus_Snapshot_*.zip")
    if zips:
        latest_mtime = max(os.path.getmtime(z) for z in zips)
        BACKUP_AGE_HOURS_GAUGE.set(round((time.time() - latest_mtime) / 3600.0, 2))
    else:
        BACKUP_AGE_HOURS_GAUGE.set(999.0)

    # 2. Read weekly drawdown & per-sleeve NAV from tripartite_60s_state.json
    state_path = r"C:\Quant-Nexus-Eng\tripartite_60s_state.json"
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            FLEET_DD_PCT_GAUGE.set(float(data.get("fleet_dd_pct", 0.0)))
            sleeves = data.get("sleeves", {})
            for sleeve_name, sleeve_info in sleeves.items():
                if isinstance(sleeve_info, dict) and "nav" in sleeve_info:
                    FLEET_NAV_GAUGE.labels(sleeve=sleeve_name).set(float(sleeve_info["nav"]))
        except Exception:
            pass

@app.get("/metrics")
def metrics_endpoint():
    refresh_operational_metrics()
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health_check():
    refresh_operational_metrics()
    return {"status": "online", "system": "QuantNexus v5.6 Governor"}

if __name__ == "__main__":
    uvicorn.run("run_server:app", host="127.0.0.1", port=8000, reload=False)
