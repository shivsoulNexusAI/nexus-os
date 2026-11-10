# -*- coding: utf-8 -*-
import sys
import os

# 1. Neutralize OpenBLAS memory heap allocations before importing numerical engines
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import json
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import httpx
from PIL import Image, ImageDraw, ImageFont

CONFIG_FILE = Path(r"C:\Quant-Nexus-Eng\telegram_config.json")
LOG_FILE = Path(r"C:\Quant-Nexus-Eng\weekly_chart.log")
DB_PATH = Path(r"C:\Quant-Nexus-Eng\nexus_telemetry.db")
OUTPUT_CHART_PATH = Path(r"C:\Quant-Nexus-Eng\weekly_performance_chart.png")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("WeeklyChartExporter")

def load_telegram_cfg():
    if not CONFIG_FILE.exists():
        return None, None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data.get("bot_token"), data.get("authorized_chat_id")
    except Exception:
        return None, None

def dispatch_chart_to_telegram(caption: str):
    token, chat_id = load_telegram_cfg()
    if not token or not chat_id:
        log.error("Missing Telegram bot configuration.")
        return

    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(OUTPUT_CHART_PATH, "rb") as img_file:
            files = {"photo": ("weekly_chart.png", img_file, "image/png")}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, data=data, files=files)
                if resp.status_code == 200:
                    log.info("Weekly performance chart dispatched successfully to Telegram.")
                else:
                    log.error("Telegram error sending photo: %s", resp.text)
    except Exception as e:
        log.error("Failed to upload chart photo: %s", e)

def render_pillow_chart(deals, net_pnl, win_rate, total_deals):
    """Zero-OpenBLAS chart generator using Pillow directly (uses <2MB RAM)."""
    width, height = 720, 360
    img = Image.new("RGB", (width, height), color="#0d1117")
    draw = ImageDraw.Draw(img)

    # Grid & borders
    draw.rectangle([(20, 20), (width - 20, height - 20)], outline="#30363d", width=1)
    draw.line([(20, 60), (width - 20, 60)], fill="#30363d", width=1)

    # Header Text
    draw.text((35, 30), "QUANTNEXUS FLEET // 7-DAY CUMULATIVE RETURN", fill="#f0f6fc")

    pnl_color = "#3fb950" if net_pnl >= 0 else "#f85149"
    draw.text((500, 30), f"Net: ${net_pnl:+,.2f}", fill=pnl_color)

    # Baseline Zero
    zero_y = int(height * 0.65)
    draw.line([(40, zero_y), (width - 40, zero_y)], fill="#8b949e", width=1)

    # Draw Cumulative Curve or Deal Bars
    if deals:
        cum_vals = []
        c = 0.0
        for d in deals:
            c += d[6]
            cum_vals.append(c)

        max_val = max(cum_vals) if max(cum_vals) > 0 else 1.0
        min_val = min(cum_vals) if min(cum_vals) < 0 else -1.0
        val_span = max(abs(max_val), abs(min_val)) or 1.0

        n = len(cum_vals)
        plot_w = width - 80
        plot_h = 100

        pts = []
        for i, val in enumerate(cum_vals):
            x = 40 + int(i * (plot_w / max(n - 1, 1)))
            y = zero_y - int((val / val_span) * plot_h)
            pts.append((x, y))

        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i+1]], fill="#58a6ff", width=2)
            
        # Draw final endpoint circle
        end_x, end_y = pts[-1]
        draw.ellipse([(end_x - 4, end_y - 4), (end_x + 4, end_y + 4)], fill=pnl_color)
    else:
        draw.text((width // 3, zero_y - 10), "Accumulating Telemetry Snapshot Data...", fill="#8b949e")

    # Footer metrics bar
    footer_text = f"Trades: {total_deals} | Win Rate: {win_rate:.1f}% | Strategy Fleet: T1, T2, T3"
    draw.text((35, height - 45), footer_text, fill="#8b949e")

    img.save(OUTPUT_CHART_PATH, format="PNG")
    log.info("Rendered clean Pillow performance chart to %s", OUTPUT_CHART_PATH)

def generate_weekly_report(days_back: int = 7):
    if not DB_PATH.exists():
        log.error("Database %s does not exist.", DB_PATH)
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    sql_deals = "SELECT time_close, login, symbol, profit, commission, swap, net_pnl FROM deals_history WHERE time_close >= ? ORDER BY time_close ASC"
    cur.execute(sql_deals, (cutoff_iso,))
    deals = cur.fetchall()
    conn.close()

    total_deals = len(deals)
    wins = len([d for d in deals if d[6] > 0])
    losses = len([d for d in deals if d[6] < 0])
    win_rate = (wins / total_deals * 100.0) if total_deals > 0 else 0.0
    net_pnl = sum(d[6] for d in deals)
    gross_win = sum(d[6] for d in deals if d[6] > 0)
    gross_loss = abs(sum(d[6] for d in deals if d[6] < 0))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.9 if gross_win > 0 else 0.0)

    render_pillow_chart(deals, net_pnl, win_rate, total_deals)

    net_icon = "🟢" if net_pnl >= 0 else "🔴"
    caption = (
        f"📊 <b>QUANTNEXUS // WEEKLY ALPHA TEAR-SHEET</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Audit Period:</b> Trailing 7 Days\n"
        f"<b>Fleet Net Return:</b> {net_icon} <code>${net_pnl:+,.2f}</code>\n"
        f"<b>Win Rate:</b> <code>{win_rate:.1f}%</code> ({wins}W / {losses}L)\n"
        f"<b>Profit Factor:</b> <code>{profit_factor:.2f}</code>\n"
        f"<b>Completed Executions:</b> <code>{total_deals} deals</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Autonomous weekly alpha audit rendered directly on VPS.</i>"
    )

    dispatch_chart_to_telegram(caption)

def daemon_loop():
    log.info("Weekly Performance Exporter Daemon running.")
    log.info("Target Schedule: Every Friday at 21:30:00 UTC (Market Close).")
    dispatched_week = None

    while True:
        now_utc = datetime.now(timezone.utc)
        current_iso_week = (now_utc.isocalendar().year, now_utc.isocalendar().week)

        if now_utc.weekday() == 4 and now_utc.hour == 21 and now_utc.minute >= 30:
            if dispatched_week != current_iso_week:
                log.info("Triggering Friday Market Close Weekly Export...")
                generate_weekly_report(days_back=7)
                dispatched_week = current_iso_week
                time.sleep(120)

        time.sleep(30)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        log.info("Manual test invocation (--now) engaged.")
        generate_weekly_report(days_back=7)
    else:
        daemon_loop()