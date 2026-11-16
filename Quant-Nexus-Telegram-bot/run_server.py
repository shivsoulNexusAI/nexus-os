import os
import json
import time
import glob
import asyncio
import httpx
import psutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from prometheus_client import Counter, Gauge, REGISTRY, generate_latest, CONTENT_TYPE_LATEST
import uvicorn

TG_TOKEN = os.getenv("NEXUS_OS_TELEGRAM_TOKEN", "9213146215:AAGNsCGLIvzrfjowmxQ32R8zbz8_YQsVTKE")
TG_CHAT_ID = os.getenv("NEXUS_OS_TELEGRAM_CHAT_ID", "5279761713")
ALERT_COOLDOWN_SEC = 3600
_last_alert_sent: dict[str, float] = {}

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

async def send_telegram_alert(key: str, text: str):
    now = time.time()
    if now - _last_alert_sent.get(key, 0) < ALERT_COOLDOWN_SEC:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json={"chat_id": TG_CHAT_ID, "text": text})
            if res.status_code == 200:
                _last_alert_sent[key] = now
    except Exception:
        pass

def refresh_operational_metrics() -> dict:
    # 1. Backup age check
    zips = glob.glob(r"C:\Quant-Nexus-Backups\QuantNexus_Snapshot_*.zip")
    backup_age_hrs = round((time.time() - max(os.path.getmtime(z) for z in zips)) / 3600.0, 2) if zips else 999.0
    BACKUP_AGE_HOURS_GAUGE.set(backup_age_hrs)

    # 2. Weekly drawdown & sleeve NAV check
    dd_pct = 0.0
    state_path = r"C:\Quant-Nexus-Eng\tripartite_60s_state.json"
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            dd_pct = float(data.get("fleet_dd_pct", 0.0))
            FLEET_DD_PCT_GAUGE.set(dd_pct)
            for sleeve_name, sleeve_info in data.get("sleeves", {}).items():
                if isinstance(sleeve_info, dict) and "nav" in sleeve_info:
                    FLEET_NAV_GAUGE.labels(sleeve=sleeve_name).set(float(sleeve_info["nav"]))
        except Exception:
            pass

    # 3. Free disk space on C:\ (GB)
    disk_free_gb = round(psutil.disk_usage("C:\\").free / (1024 ** 3), 2)
    return {"backup_age_hrs": backup_age_hrs, "dd_pct": dd_pct, "disk_free_gb": disk_free_gb}

async def watchdog_loop():
    while True:
        try:
            stats = refresh_operational_metrics()
            if stats["dd_pct"] >= 2.2:
                await send_telegram_alert(
                    "dd_warn",
                    f"🚨 QUANTNEXUS DRAWDOWN WARNING\nWeekly DD reached {stats['dd_pct']:.2f}% (Circuit Breaker at 3.00% / $90)."
                )
            if stats["backup_age_hrs"] > 25.0:
                await send_telegram_alert(
                    "backup_stale",
                    f"⚠️ QUANTNEXUS BACKUP STALE\nLast ZIP snapshot was {stats['backup_age_hrs']:.1f}h ago (> 25h threshold)."
                )
            if stats["disk_free_gb"] < 1.5:
                await send_telegram_alert(
                    "disk_low",
                    f"⚠️ VPS DISK SPACE LOW\nOnly {stats['disk_free_gb']:.2f} GB free on C:\\."
                )
        except Exception:
            pass
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(watchdog_loop())
    yield
    task.cancel()

app = FastAPI(title="QuantNexus Governor", lifespan=lifespan)

@app.get("/metrics")
def metrics_endpoint():
    refresh_operational_metrics()
    return Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health_check():
    stats = refresh_operational_metrics()
    return {"status": "online", "system": "QuantNexus v5.6 Governor", **stats}

if __name__ == "__main__":
    uvicorn.run("run_server:app", host="127.0.0.1", port=8000, reload=False)
