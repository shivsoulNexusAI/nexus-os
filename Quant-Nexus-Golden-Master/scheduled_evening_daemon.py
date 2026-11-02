import os
import sys
import time
import csv
import argparse
from datetime import datetime, timedelta, timezone
import MetaTrader5 as mt5
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import requests

# ------------------------------------------------------------------------------
# 1. Environment & Paths
# ------------------------------------------------------------------------------
load_dotenv(override=True)

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
CREDENTIALS_FILE = os.path.join(BASE_DIR, "google_credentials.json")
SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "10NWy4DvXEiEqUJ2nYus_x-uVH60mUovsFcFKnSuVJTQ").strip()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

RAW_TRADES_HEADER = [
    "Timestamp UTC", "Ticket", "Asset", "Action", "Volume",
    "Entry Price", "Exit Price", "SL", "TP1", "TP2",
    "Profit USD", "Strategy", "Quant Score", "Exit Reason"
]

# ------------------------------------------------------------------------------
# 2. MT5 & Google Sheets Logic
# ------------------------------------------------------------------------------
def fetch_mt5_deals(days: int = 1):
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        return []

    from_date = datetime.now(timezone.utc) - timedelta(days=days)
    to_date = datetime.now(timezone.utc) + timedelta(minutes=5)
    deals = mt5.history_deals_get(from_date, to_date)
    mt5.shutdown()

    if deals is None:
        return []

    closed_deals = [d for d in deals if d.entry in (1, 2, 3) and (d.profit != 0 or d.symbol != "")]
    return closed_deals

def sync_deals_to_sheets(deals, dry_run: bool = False):
    if dry_run:
        print("🛡️ [DRY-RUN] Skipping Google Sheets API append.")
        return f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID} [SIMULATED]"

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Credentials file missing: {CREDENTIALS_FILE}")
        return None

    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        ws = spreadsheet.worksheet("Raw_Trades")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title="Raw_Trades", rows="2000", cols="15")

    existing_records = ws.get_all_values()
    existing_tickets = set()
    if len(existing_records) > 1:
        for row in existing_records[1:]:
            if len(row) > 1 and row[1]:
                existing_tickets.add(str(row[1]).strip())

    new_rows = []
    for d in deals:
        ticket_str = str(d.ticket)
        if ticket_str in existing_tickets:
            continue

        dt_utc = datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        action = "BUY" if d.type == 0 else ("SELL" if d.type == 1 else "OTHER")
        net_profit = round(float(d.profit + d.commission + d.swap), 2)
        comment = str(d.comment) if d.comment else "Regular_Exit"

        new_rows.append([
            dt_utc,
            ticket_str,
            str(d.symbol),
            action,
            float(d.volume),
            0.0,
            float(d.price),
            0.0,
            0.0,
            0.0,
            net_profit,
            f"Magic_{d.magic}",
            95.0,
            comment
        ])

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"✅ Appended {len(new_rows)} new deals to Google Sheets.")
    else:
        print("ℹ️ No new deals to append to sheet.")

    return spreadsheet.url

# ------------------------------------------------------------------------------
# 3. Telegram Report Dispatch
# ------------------------------------------------------------------------------
def generate_and_dispatch_report(deals, sheet_url, dry_run: bool = False):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    csv_filename = os.path.join(BASE_DIR, f"daily_report_{today_str}.csv")

    total_pnl = 0.0
    wins = 0
    losses = 0

    with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(RAW_TRADES_HEADER)
        for d in deals:
            dt_utc = datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            action = "BUY" if d.type == 0 else "SELL"
            net_profit = round(float(d.profit + d.commission + d.swap), 2)
            total_pnl += net_profit
            if net_profit > 0:
                wins += 1
            elif net_profit < 0:
                losses += 1

            writer.writerow([
                dt_utc, d.ticket, d.symbol, action, d.volume,
                0.0, d.price, 0.0, 0.0, 0.0,
                net_profit, f"Magic_{d.magic}", 95.0, d.comment
            ])

    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0

    caption = (
        f"📊 *Quant Nexus - Daily Institutional Report*\n"
        f"📅 Date: `{today_str}` (21:00 UTC Close)\n\n"
        f"• *Closed Trades*: `{len(deals)}`\n"
        f"• *Net Realized P&L*: `${total_pnl:+.2f}`\n"
        f"• *Win Rate*: `{win_rate:.1f}%` ({wins}W / {losses}L)\n\n"
        f"🔗 [Open Live Master Ledger]({sheet_url})"
    )

    if dry_run:
        print("\n" + "=" * 60)
        print("🛡️ [DRY-RUN] Telegram Message Simulated (Not Sent):")
        print(caption)
        print(f"• Generated Local CSV: {csv_filename} ({os.path.getsize(csv_filename)} bytes)")
        print("=" * 60 + "\n")
        if os.path.exists(csv_filename):
            os.remove(csv_filename)
        return

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_doc_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        try:
            with open(csv_filename, "rb") as doc:
                files = {"document": doc}
                data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
                requests.post(send_doc_url, data=data, files=files, timeout=20)
            print("📨 Daily report and CSV dispatched to Telegram.")
        except Exception as e:
            print(f"⚠️ Telegram send error: {e}")
    else:
        print("⚠️ Telegram token or chat ID missing in .env. Skipped message push.")

    if os.path.exists(csv_filename):
        try:
            os.remove(csv_filename)
        except Exception:
            pass

# ------------------------------------------------------------------------------
# 4. Execution Controller
# ------------------------------------------------------------------------------
def run_evening_job(dry_run: bool = False):
    mode_tag = "[DRY-RUN] " if dry_run else ""
    print(f"\n⏰ {mode_tag}[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] Running evening routine...")
    deals = fetch_mt5_deals(days=1)
    sheet_url = sync_deals_to_sheets(deals, dry_run=dry_run)
    generate_and_dispatch_report(deals, sheet_url, dry_run=dry_run)
    print(f"✨ {mode_tag}Evening routine finished.\n")

def daemon_loop(dry_run: bool = False):
    print("🚀 Quant Nexus Evening Daemon initialized.")
    if dry_run:
        print("🛡️ RUNNING IN DRY-RUN MODE: No writes or Telegram alerts will be issued.")
    print("⏳ Waiting for 21:00 UTC daily trigger...")
    has_run_today = False

    while True:
        now = datetime.now(timezone.utc)
        if now.hour == 21 and now.minute == 0 and not has_run_today:
            run_evening_job(dry_run=dry_run)
            has_run_today = True
            time.sleep(60)

        if now.hour == 0 and has_run_today:
            has_run_today = False

        time.sleep(15)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evening automated export daemon.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate extraction, CSV generation, and message formatting without sending network writes."
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Execute the job immediately once instead of waiting in the daemon scheduling loop."
    )
    args = parser.parse_args()

    if args.now:
        run_evening_job(dry_run=args.dry_run)
    else:
        daemon_loop(dry_run=args.dry_run)