import os
import sys
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

# ------------------------------------------------------------------------------
# 1. Environment & Path Resolution
# ------------------------------------------------------------------------------
load_dotenv(override=True)

BASE_DIR = r"C:\Quant-Nexus-Eng\Quant-Nexus-Telegram-bot"
CREDENTIALS_FILE = os.path.join(BASE_DIR, "google_credentials.json")
SPREADSHEET_NAME = "Quant Nexus Master Ledger"

# Fallback: paste your raw sheet ID here if not in .env
DEFAULT_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ------------------------------------------------------------------------------
# 2. Main Dashboard Setup Routine
# ------------------------------------------------------------------------------
def setup_quant_nexus_dashboard():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Error: {CREDENTIALS_FILE} not found.")
        sys.exit(1)

    print("🔑 Authenticating with Google Cloud...")
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)

    # 1. Connect to Spreadsheet (ID first, Title fallback)
    spreadsheet = None
    sheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID).strip()

    if sheet_id:
        print(f"🌐 Connecting using Spreadsheet ID: {sheet_id}...")
        try:
            spreadsheet = client.open_by_key(sheet_id)
        except Exception as e:
            print(f"⚠️ Failed connecting via ID: {e}")

    if not spreadsheet:
        print(f"🌐 Falling back to Title search: '{SPREADSHEET_NAME}'...")
        try:
            spreadsheet = client.open(SPREADSHEET_NAME)
        except Exception as e:
            print(f"❌ Could not open sheet by title: {e}")
            print("💡 Solution: Set GOOGLE_SPREADSHEET_ID in your .env or check service account share permissions.")
            sys.exit(1)

    print(f"✅ Connected to: '{spreadsheet.title}'")

    existing_tabs = [ws.title for ws in spreadsheet.worksheets()]

    # 2. Setup or verify 'Raw_Trades' tab
    if "Raw_Trades" not in existing_tabs:
        print("📄 Creating 'Raw_Trades' tab...")
        ws_raw = spreadsheet.add_worksheet(title="Raw_Trades", rows="2000", cols="15")
        raw_headers = [
            "Timestamp UTC", "Ticket", "Asset", "Action", "Volume",
            "Entry Price", "Exit Price", "SL", "TP1", "TP2",
            "Profit USD", "Strategy", "Quant Score", "Exit Reason"
        ]
        ws_raw.append_row(raw_headers, value_input_option="USER_ENTERED")
    else:
        print("✔ 'Raw_Trades' tab verified.")

    # 3. Setup or reset 'Dashboard' tab
    if "Dashboard" in existing_tabs:
        print("🔄 Clearing existing 'Dashboard' tab...")
        ws_dash = spreadsheet.worksheet("Dashboard")
        ws_dash.clear()
    else:
        print("📄 Creating 'Dashboard' tab...")
        ws_dash = spreadsheet.add_worksheet(title="Dashboard", rows="50", cols="12")

    # 4. Inject Institutional KPI Structure & Formulas
    print("📊 Injecting dynamic KPI formulas and query blocks...")

    # Block 1: Executive Portfolio Metrics (Cols A & B)
    kpi_block = [
        ["METRIC", "VALUE"],
        ["Total Realized P&L ($)", "=SUM(Raw_Trades!K2:K)"],
        ["Total Closed Trades", "=COUNT(Raw_Trades!K2:K)"],
        ["Winning Trades", '=COUNTIF(Raw_Trades!K2:K, ">0")'],
        ["Losing Trades", '=COUNTIF(Raw_Trades!K2:K, "<0")'],
        ["Win Rate (%)", "=IFERROR(B4/(B4+B5), 0)"],
        ["Profit Factor", '=IFERROR(SUMIF(Raw_Trades!K2:K, ">0") / ABS(SUMIF(Raw_Trades!K2:K, "<0")), 0)'],
        ["Average Win ($)", '=IFERROR(AVERAGEIF(Raw_Trades!K2:K, ">0"), 0)'],
        ["Average Loss ($)", '=IFERROR(AVERAGEIF(Raw_Trades!K2:K, "<0"), 0)'],
        ["Payoff Ratio (RRR)", "=IFERROR(B8 / ABS(B9), 0)"]
    ]
    ws_dash.update(values=kpi_block, range_name="A1:B10", value_input_option="USER_ENTERED")

    # Block 2: Periodic P&L Breakdown (Cols D & E)
    periodic_block = [
        ["PERIOD", "P&L ($)"],
        ["Today (UTC)", '=SUMIFS(Raw_Trades!K2:K, Raw_Trades!A2:A, ">="&TEXT(TODAY(), "yyyy-mm-dd"))'],
        ["Past 7 Days", '=SUMIFS(Raw_Trades!K2:K, Raw_Trades!A2:A, ">="&TEXT(TODAY()-7, "yyyy-mm-dd"))'],
        ["This Month (MTD)", '=SUMIFS(Raw_Trades!K2:K, Raw_Trades!A2:A, ">="&TEXT(DATE(YEAR(TODAY()), MONTH(TODAY()), 1), "yyyy-mm-dd"))'],
        ["Trades Today", '=COUNTIFS(Raw_Trades!A2:A, ">="&TEXT(TODAY(), "yyyy-mm-dd"))']
    ]
    ws_dash.update(values=periodic_block, range_name="D1:E5", value_input_option="USER_ENTERED")

    # Block 3: Dynamic Asset Breakdown Query (Cell G1)
    asset_query = [
        ["=QUERY(Raw_Trades!C2:K, \"SELECT C, COUNT(K), SUM(K), AVG(K) WHERE C IS NOT NULL GROUP BY C LABEL C 'Asset', COUNT(K) 'Total Trades', SUM(K) 'Total P&L ($)', AVG(K) 'Avg Trade ($)'\", 0)"]
    ]
    ws_dash.update(values=asset_query, range_name="G1", value_input_option="USER_ENTERED")

    # 5. Apply Visual Cell Formats
    print("🎨 Applying institutional formatting (Currency, Percent, Bolds)...")
    sheet_id_int = ws_dash.id

    requests = [
        # Format B2 (Total Realized P&L) -> Currency Bold
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id_int,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"},
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat(numberFormat,textFormat)"
            }
        },
        # Format B6 (Win Rate %) -> Percentage Bold
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id_int,
                    "startRowIndex": 5,
                    "endRowIndex": 6,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "PERCENT", "pattern": "0.0%"},
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat(numberFormat,textFormat)"
            }
        },
        # Format B8:B9 (Avg Win / Avg Loss) -> Currency
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id_int,
                    "startRowIndex": 7,
                    "endRowIndex": 9,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}
                    }
                },
                "fields": "userEnteredFormat(numberFormat)"
            }
        },
        # Format E2:E4 (Periodic P&L) -> Currency Bold
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id_int,
                    "startRowIndex": 1,
                    "endRowIndex": 4,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"},
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat(numberFormat,textFormat)"
            }
        }
    ]

    try:
        spreadsheet.batch_update({"requests": requests})
        print("✨ Cell formatting applied successfully.")
    except Exception as exc:
        print(f"⚠️ Formatting note: {exc}")

    print("\n🎉 DASHBOARD READY! No manual spreadsheet configuration required.")
    print(f"🔗 Live Google Sheet: {spreadsheet.url}")


if __name__ == "__main__":
    setup_quant_nexus_dashboard()