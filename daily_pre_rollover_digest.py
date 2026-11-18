# -*- coding: utf-8 -*-
"""
QUANT-NEXUS DAILY PRE-ROLLOVER PNL & PROFIT FACTOR DIGEST (21:40 UTC)
Audits Silo 1 (#278062038), Silo 2 (#278062039), and Silo 3 (#278062042)
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
import httpx
import MetaTrader5 as mt5

ROOT_DIR = Path(r"C:\Quant-Nexus-Eng")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TG_TOKEN = ""
TG_CHAT_ID = ""
for cfg_mod in ("telegram_nexus_config", "telegram_config", "nexus_tg_config"):
    try:
        m = __import__(cfg_mod)
        TG_TOKEN = getattr(m, "BOT_TOKEN", getattr(m, "TELEGRAM_BOT_TOKEN", getattr(m, "TOKEN", TG_TOKEN)))
        TG_CHAT_ID = str(getattr(m, "CHAT_ID", getattr(m, "TELEGRAM_CHAT_ID", getattr(m, "CHANNEL_ID", TG_CHAT_ID))))
        if TG_TOKEN and TG_CHAT_ID:
            break
    except Exception:
        pass

try:
    from telegram_notifier_v43 import send_v43_alert as _v43_send
except Exception:
    _v43_send = None

SILOS = [
    {
        "tag": "T1",
        "name": "Apex Satellite",
        "login": 278062038,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\Program Files\MetaTrader 5 - Apex Satellite\terminal64.exe",
    },
    {
        "tag": "T2",
        "name": "Pending FX",
        "login": 278062039,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_Pending_278041169\terminal64.exe",
    },
    {
        "tag": "T3",
        "name": "HFT Gold",
        "login": 278062042,
        "password": "H@ngkook3695",
        "server": "Exness-MT5Trial5",
        "path": r"C:\MT5_HFT_278041671\terminal64.exe",
    },
]

def send_telegram_report(html_text: str):
    if _v43_send is not None:
        _v43_send(html_text)
        return
    if TG_TOKEN and TG_CHAT_ID:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        with httpx.Client(timeout=10.0) as client:
            client.post(url, json={
                "chat_id": TG_CHAT_ID,
                "text": html_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            })

def audit_silo_today(silo: dict, day_start_utc: datetime, now_utc: datetime) -> dict:
    if not mt5.initialize(path=silo["path"], login=silo["login"], password=silo["password"], server=silo["server"], portable=False):
        return {"ok": False, "error": str(mt5.last_error())}

    acct = mt5.account_info()
    if not acct:
        mt5.shutdown()
        return {"ok": False, "error": "account_info_none"}

    deals = mt5.history_deals_get(day_start_utc, now_utc) or []
    closed = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]

    pnls = [float(d.profit + d.swap + d.commission) for d in closed]
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    net_pnl = sum(pnls)
    wins = len([p for p in pnls if p > 0])
    total = len(pnls)
    win_rate = (wins / total * 100.0) if total > 0 else 0.0
    pf_str = f"{(gross_win / gross_loss):.2f}" if gross_loss > 0 else ("INF" if gross_win > 0 else "0.00")

    positions = mt5.positions_get() or []
    pending = mt5.orders_get() or []

    res = {
        "ok": True,
        "balance": float(acct.balance),
        "equity": float(acct.equity),
        "floating": float(acct.profit),
        "trades": total,
        "wins": wins,
        "win_rate": win_rate,
        "gross_win": gross_win,
        "gross_loss": gross_loss,
        "net_pnl": net_pnl,
        "pf_str": pf_str,
        "open_count": len(positions),
        "pending_count": len(pending),
    }
    mt5.shutdown()
    return res

def build_and_send_digest():
    now_utc = datetime.now(timezone.utc)
    day_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    fleet_equity = 0.0
    fleet_net = 0.0
    fleet_gw = 0.0
    fleet_gl = 0.0
    fleet_trades = 0
    fleet_wins = 0
    lines = []

    for s in SILOS:
        st = audit_silo_today(s, day_start_utc, now_utc)
        if not st["ok"]:
            lines.append(f"⚠️ <b>{s['tag']} (#{s['login']})</b>: Offline ({st['error']})")
            continue

        fleet_equity += st["equity"]
        fleet_net += st["net_pnl"]
        fleet_gw += st["gross_win"]
        fleet_gl += st["gross_loss"]
        fleet_trades += st["trades"]
        fleet_wins += st["wins"]

        pnl_icon = "🟢" if st["net_pnl"] >= 0 else "🔴"
        lines.append(
            f"{pnl_icon} <b>{s['tag']} • {s['name']}</b> (<code>#{s['login']}</code>)\n"
            f"   Eq: <code>${st['equity']:.2f}</code> | Float: <code>{st['floating']:+.2f}</code>\n"
            f"   Today: <b><code>{st['net_pnl']:+.2f}</code></b> ({st['trades']}T, WR <code>{st['win_rate']:.1f}%</code>, PF <b><code>{st['pf_str']}</code></b>)\n"
            f"   Book: {st['open_count']} Open / {st['pending_count']} Pending"
        )

    fleet_wr = (fleet_wins / fleet_trades * 100.0) if fleet_trades > 0 else 0.0
    fleet_pf = f"{(fleet_gw / fleet_gl):.2f}" if fleet_gl > 0 else ("INF" if fleet_gw > 0 else "0.00")
    header_icon = "📈" if fleet_net >= 0 else "📉"

    report = (
        f"{header_icon} <b>[QUANT-NEXUS DAILY PRE-ROLLOVER DIGEST]</b>\n"
        f"🕒 <code>{now_utc.strftime('%Y-%m-%d %H:%M UTC')}</code> (5m to Rollover Guard)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines) +
        f"\n━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 <b>FLEET TOTALS</b>\n"
        f"• Total Equity: <b><code>${fleet_equity:.2f}</code></b>\n"
        f"• Daily Net PnL: <b><code>{fleet_net:+.2f}</code></b> ({fleet_trades} Trades)\n"
        f"• Fleet Win Rate: <code>{fleet_wr:.1f}%</code> | Profit Factor: <b><code>{fleet_pf}</code></b>"
    )

    send_telegram_report(report)
    print(report)

if __name__ == "__main__":
    build_and_send_digest()
