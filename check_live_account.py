import shutil
import MetaTrader5 as mt5

free_mb = round(shutil.disk_usage("C:\\").free / (1024 * 1024), 2)
if mt5.initialize(path=r"C:/MT5_Quant_278061453/terminal64.exe", portable=False):
    a = mt5.account_info()
    print(f"C: Free Space: {free_mb} MB | MT5 #{a.login} | Balance: ${a.balance:.2f} | Equity: ${a.equity:.2f} | Free Margin: ${a.margin_free:.2f} | Open Pos: {mt5.positions_total()} | Pending Orders: {mt5.orders_total()}")
    mt5.shutdown()