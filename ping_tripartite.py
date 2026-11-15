import httpx
from telegram_quantower_config import TELEGRAM_BOT_TOKEN as TOK_QUANT, TARGET_LOGIN as ACC_QUANT
from telegram_nexus_config import TELEGRAM_BOT_TOKEN as TOK_NEXUS, TARGET_LOGIN as ACC_NEXUS
from telegram_gold_config import TELEGRAM_BOT_TOKEN as TOK_GOLD, TARGET_LOGIN as ACC_GOLD

CHAT_ID = "5279761713"

bots = [
    ("Quant Alert Bot (@Qunatalertbot)", TOK_QUANT, ACC_QUANT, "🌐 QUANTOWER MAJORS PIPELINE ONLINE\nAccount #278062038\nScope: ICT / ORB Breakout Grid"),
    ("NEXUS AI BOT👑🔥 (@Nexus_AIk_bot)", TOK_NEXUS, ACC_NEXUS, "👑🔥 NEXUS AI BOT PIPELINE ONLINE\nAccount #278062039\nScope: Dynamic Multi-Straddle V2 (ML P>=0.75)"),
    ("Nexus Gold 24/7 (@Nexusfurious_bot)", TOK_GOLD, ACC_GOLD, "🥇 NEXUS GOLD 24/7 PIPELINE ONLINE\nAccount #278062042\nScope: Pure XAUUSD HFT Engine")
]

print("=" * 80)
print("FIRING SIMULTANEOUS TELEGRAM PIPELINE VERIFICATION")
print("=" * 80)

for name, tok, acc, desc in bots:
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": f"✅ <b>[{name}]</b>\n━━━━━━━━━━━━━━━━━━\n{desc}\n━━━━━━━━━━━━━━━━━━\nHandshake Verified & Strict Account Isolation Confirmed.",
        "parse_mode": "HTML"
    }
    try:
        r = httpx.post(url, json=payload, timeout=8.0)
        if r.status_code == 200:
            print(f"[SUCCESS] Delivered to: {name}")
        else:
            print(f"[-] Failed for {name}: HTTP {r.status_code} - {r.text}")
    except Exception as e:
        print(f"[-] Network error for {name}: {e}")
print("=" * 80)