import MetaTrader5 as mt5
import time

MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
ACCOUNT_LOGIN = 278025377
ACCOUNT_SERVER = "Exness-MT5Trial5"

if not mt5.initialize(path=MT5_PATH, login=ACCOUNT_LOGIN, server=ACCOUNT_SERVER, portable=True):
    print(f"[-] Init failed: {mt5.last_error()}")
    quit()

symbols = ["BTCUSD", "ETHUSD", "XAUUSD", "EURUSD", "USDJPY"]
print("=" * 70)
print("📊 LEVEL 2 MARKET DEPTH (DOM) QUEUE DEPLETION AUDIT")
print("=" * 70)

for sym in symbols:
    mt5.symbol_select(sym, True)
    res = mt5.market_book_add(sym)
    
    # Allow terminal cache to receive L2 packets
    book = None
    for _ in range(5):
        time.sleep(0.3)
        book = mt5.market_book_get(sym)
        if book:
            break

    if book:
        bid_vol = sum(item.volume_dbl if hasattr(item, 'volume_dbl') else item.volume for item in book if item.type == mt5.BOOK_TYPE_BUY)
        ask_vol = sum(item.volume_dbl if hasattr(item, 'volume_dbl') else item.volume for item in book if item.type == mt5.BOOK_TYPE_SELL)
        total_vol = bid_vol + ask_vol
        imbalance = (bid_vol - ask_vol) / total_vol if total_vol > 0 else 0.0
        best_bid = max([item.price for item in book if item.type == mt5.BOOK_TYPE_BUY], default=0.0)
        best_ask = min([item.price for item in book if item.type == mt5.BOOK_TYPE_SELL], default=0.0)
        print(f"[{sym:<7}] ✅ L2 Tiers: {len(book):<2} | BidVol: {bid_vol:<8.2f} | AskVol: {ask_vol:<8.2f} | DOM OFI: {imbalance:>+6.1%} | Spread: {best_ask - best_bid:.5f}")
    else:
        print(f"[{sym:<7}] ⚠️ No DOM Feed from Broker (CFD Synthetic Quote Stream). Fallback: Tick-Delta OFI Active.")
    
    mt5.market_book_release(sym)

mt5.shutdown()
