import asyncio
import MetaTrader5 as mt5

# Registered account registry (add additional accounts as needed)
ACCOUNT_VAULT = {
    "PRIMARY": {
        "login": 278013334,
        "server": "Exness-MT5Real16",
        "label": "Master Exness Live"
    }
}

BRIDGE_LOCK = asyncio.Lock()

async def hot_swap_mt5_account(account_key: str, password: str = None, server: str = None) -> tuple[bool, str]:
    async with BRIDGE_LOCK:
        try:
            # 1. Determine target credentials
            if account_key.upper() in ACCOUNT_VAULT:
                target = ACCOUNT_VAULT[account_key.upper()]
                login = target["login"]
                srv = target["server"]
                label = target["label"]
            else:
                # Direct login number supplied
                try:
                    login = int(account_key)
                except ValueError:
                    return False, f"Invalid account identifier: {account_key}"
                srv = server or "Exness-MT5Real16"
                label = f"Account #{login}"

            # 2. Graceful teardown of active IPC pipes
            mt5.shutdown()
            await asyncio.sleep(0.75)  # Allow Windows named pipes to fully release

            # 3. Clean re-initialization
            init_params = {"login": login, "server": srv, "timeout": 15000}
            if password:
                init_params["password"] = password

            ok = mt5.initialize(**init_params)
            if not ok:
                err = mt5.last_error()
                return False, f"MT5 connection failed: {err}"

            acc = mt5.account_info()
            if not acc:
                return False, "Connected but failed to fetch account telemetry."

            msg = (
                "🔄 <b>ACCOUNT HOT-SWAP SUCCESSFUL</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<pre>\n"
                "┌ ACCOUNT BRIDGE ──────────────────┐\n"
                f"│ Status:  CONNECTED & VERIFIED    │\n"
                f"│ Label:   {label[:22]}\n"
                f"│ Login:   #{acc.login}\n"
                f"│ Server:  {acc.server[:22]}\n"
                f"│ Equity:  ${acc.equity:,.2f}\n"
                f"│ Balance: ${acc.balance:,.2f}\n"
                "└──────────────────────────────────┘\n"
                "</pre>"
            )
            return True, msg

        except Exception as e:
            return False, f"Bridge critical fault: {str(e)}"
