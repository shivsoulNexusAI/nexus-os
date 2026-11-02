import os
import sys
import argparse
from datetime import datetime, timedelta, timezone
import MetaTrader5 as mt5
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

# ------------------------------------------------------------------------------
# 1. Environment & Configuration
# ------------------------------------------------------------------------------
load_dotenv(override=True)

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
CREDENTIALS_FILE = os.path.join(BASE_DIR, "google_credentials.json")
SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "10NWy4DvXEiEqUJ2nYus_x-uVH60mUovsFcFKnSuVJTQ").strip()

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
# 2. Main Extraction and Sync
# ------------------------------------------------------------------------------
def sync_mt5_history_to_ledger(lookback_days: int = 30, dry_run: bool = False):
    print("🔌 Initializing MetaTrader 5 API...")
    if not mt5.initialize():
        print(f"❌ MT5 initialization failed: {mt5.last_error()}")
        sys.exit(1)

    terminal_info = mt5.terminal_info()
    account_info = mt5.account_info()
    print(f"✅ Connected to MT5: {terminal_info.name} (Account: {account_info.login})")

    from_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    to_date = datetime.now(timezone.utc) + timedelta(days=1)

    print(f"🔍 Fetching closed deals ({lookback_days}d window: {from_date.strftime('%Y-%m-%d')} to now)...")
    deals = mt5.history_deals_get(from_date, to_date)
    mt5.shutdown()

    if deals is None:
        print("❌ Failed to retrieve deal history.")
        sys.exit(1)

    # Filter for exit transactions (entry in DEAL_ENTRY_OUT / DEAL_ENTRY_INOUT)
    trade_deals = [d for d in deals if d.entry in (1, 2, 3) and (d.profit != 0 or d.symbol != "")]
    print(f"✅ Identified {len(trade_deals)} closed deal records.")

    sheet_payload = [RAW_TRADES_HEADER]
    for d in trade_deals:
        dt_utc = datetime.fromtimestamp(d.time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        action = "BUY" if d.type == 0 else ("SELL" if d.type == 1 else "OTHER")
        net_profit = round(float(d.profit + d.commission + d.swap), 2)
        comment = str(d.comment) if d.comment else "Regular_Exit"

        sheet_payload.append([
            dt_utc,
            str(d.ticket),
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

    # --- Dry-Run Intercept ---
    if dry_run:
        print("\n" + "=" * 60)
        print("🛡️ [DRY-RUN MODE ACTIVE] - No changes written to Google Sheets.")
        print(f"• Total Rows Prepared: {len(sheet_payload) - 1}")
        if len(sheet_payload) > 1:
            print("• Sample record (first row):")
            for col_name, val in zip(RAW_TRADES_HEADER, sheet_payload[1]):
                print(f"    {col_name:15}: {val}")
        print("=" * 60 + "\n")
        return

    # --- Live Write Mode ---
    print("🔑 Authenticating with Google Cloud...")
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Credentials file not found: {CREDENTIALS_FILE}")
        sys.exit(1)

    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        ws = spreadsheet.worksheet("Raw_Trades")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title="Raw_Trades", rows="2000", cols="15")

    if len(sheet_payload) > 1:
        print(f"🚀 Overwriting 'Raw_Trades' with {len(sheet_payload) - 1} records...")
        ws.clear()
        ws.update(values=sheet_payload, range_name="A1", value_input_option="USER_ENTERED")
        print("🎉 Sync complete! Sheet updated.")
    else:
        print("ℹ️ No closed trade records found to sync.")

    print(f"🔗 Open Sheet: {spreadsheet.url}")

# ------------------------------------------------------------------------------
# 3. CLI Entry Point
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synchronize closed MT5 deals into the Master Ledger.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate deal extraction and payload parsing without writing to Google Sheets."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days of history to fetch (default: 30)."
    )
    args = parser.parse_args()

    sync_mt5_history_to_ledger(lookback_days=args.days, dry_run=args.dry_run)