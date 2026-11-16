import os
import json
import time
import glob
import shutil
import asyncio
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from prometheus_client import Counter, Gauge, REGISTRY, generate_latest, CONTENT_TYPE_LATEST
import uvicorn

TG_TOKEN = os.getenv("NEXUS_OS_TELEGRAM_TOKEN", "9213146215:AAGNsCGLIvzrfjowmxQ32R8zbz8_YQsVTKE")
TG_CHAT_ID = os.getenv("NEXUS_OS_TELEGRAM_CHAT_ID", "5279761713")
ALERT_COOLDOWN_SEC = 3600
_last_alert_sent: dict[str, float] = {}

SLEEVE_ALIASES = {
    "T1": "T1_BTCUSD",
    "278062038": "T1_BTCUSD",
    "T2": "T2_FX_MAJORS",
    "278062039": "T2_FX_MAJORS",
    "T3": "T3_XAUUSD",
    "278062042": "T3_XAUUSD",
}

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
DISK_FREE_GB_GAUGE = get_or_create_gauge('quant_vps_disk_free_gb', 'Free disk space on C drive in GB')
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

def _load_json_safe(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}

def refresh_operational_metrics() -> dict:
    # 1. Backup age check
    zips = glob.glob(r"C:\Quant-Nexus-Backups\QuantNexus_Snapshot_*.zip")
    backup_age_hrs = round((time.time() - max(os.path.getmtime(z) for z in zips)) / 3600.0, 2) if zips else 999.0
    BACKUP_AGE_HOURS_GAUGE.set(backup_age_hrs)

    # 2. Load weekly_nav_anchor.json (default $3,000.00 baseline across T1/T2/T3)
    anchor_data = _load_json_safe(r"C:\Quant-Nexus-Eng\weekly_nav_anchor.json")
    anchor_total = float(
        anchor_data.get("fleet_anchor_nav")
        or anchor_data.get("total_anchor_nav")
        or anchor_data.get("anchor_nav")
        or 3000.0
    )

    # 3. Map tripartite_60s_state.json across nested or flat sleeve schemas
    state_data = _load_json_safe(r"C:\Quant-Nexus-Eng\tripartite_60s_state.json")
    sleeve_navs: dict[str, float] = {}

    containers = [state_data.get("sleeves"), state_data.get("accounts"), state_data]
    for container in containers:
        if not isinstance(container, dict):
            continue
        for raw_key, val in container.items():
            matched_label = None
            for alias, canonical in SLEEVE_ALIASES.items():
                if alias in str(raw_key):
                    matched_label = canonical
                    break
            if not matched_label:
                continue

            if isinstance(val, dict):
                nav_val = val.get("nav") or val.get("equity") or val.get("balance")
                if nav_val is not None:
                    sleeve_navs[matched_label] = float(nav_val)
            elif isinstance(val, (int, float)):
                sleeve_navs[matched_label] = float(val)

    for sleeve_label, nav in sleeve_navs.items():
        FLEET_NAV_GAUGE.labels(sleeve=sleeve_label).set(nav)

    # 4. Resolve drawdown % directly from state or compute from live vs anchor NAV
    raw_dd = (
        state_data.get("fleet_dd_pct")
        if state_data.get("fleet_dd_pct") is not None
        else state_data.get("drawdown_pct")
    )
    if raw_dd is not None:
        dd_pct = round(float(raw_dd), 3)
    elif sleeve_navs and anchor_total > 0:
        live_total = sum(sleeve_navs.values())
        dd_pct = round(max(0.0, ((anchor_total - live_total) / anchor_total) * 100.0), 3)
    else:
        dd_pct = 0.0

    FLEET_DD_PCT_GAUGE.set(dd_pct)

    # 5. Free disk space on C:\ (GB) via stdlib shutil
    disk_free_gb = round(shutil.disk_usage("C:\\").free / (1024 ** 3), 2)
    DISK_FREE_GB_GAUGE.set(disk_free_gb)

    return {
        "backup_age_hrs": backup_age_hrs,
        "anchor_nav": anchor_total,
        "sleeve_navs": sleeve_navs,
        "dd_pct": dd_pct,
        "disk_free_gb": disk_free_gb,
    }

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
