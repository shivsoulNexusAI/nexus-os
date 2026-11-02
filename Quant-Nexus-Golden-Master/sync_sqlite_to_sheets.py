import os
import sys
import sqlite3
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv(override=True)

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
CREDENTIALS_FILE = os.path.join(BASE_DIR, "google_credentials.json")
DB_FILE = os.path.join(BASE_DIR, "quant_metrics.db")
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

def run_sync():
    print("🔑 Authenticating with Google Cloud...")
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    ws = spreadsheet.worksheet("Raw_Trades")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signal_history ORDER BY id ASC")
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    conn.close()

    col_map = {name: i for i, name in enumerate(cols)}
    payload = [RAW_TRADES_HEADER]

    for r in rows:
        ts = r[col_map.get("timestamp", 1)]
        asset = r[col_map.get("asset", 2)]
        direction = r[col_map.get("direction", 3)]
        rrr = r[col_map.get("rrr", 4)] or 2.0
        score = r[col_map.get("quant_score", 5)] or 0.0
        executed = r[col_map.get("executed", 6)]
        ticket = r[col_map.get("ticket", 7)] or 0

        # Construct safe row
        payload.append([
            str(ts),
            str(ticket) if ticket != 0 else "SIGNAL_ONLY",
            str(asset),
            str(direction),
            0.01,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            f"RRR_{rrr}",
            float(score),
            "Executed" if executed == 1 else "Pending_Signal"
        ])

    print(f"🚀 Updating 'Raw_Trades' with {len(payload)-1} records...")
    ws.clear()
    ws.update(values=payload, range_name="A1", value_input_option="USER_ENTERED")
    print("🎉 Sync complete! Sheet updated.")

if __name__ == "__main__":
    run_sync()