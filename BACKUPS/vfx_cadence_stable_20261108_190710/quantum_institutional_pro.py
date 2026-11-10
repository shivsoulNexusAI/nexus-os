import random
import os, sys, re, json, math, time, socket, asyncio, logging, html
from collections import Counter
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import httpx
import MetaTrader5 as mt5

try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

CFG_DIR = Path(os.getenv("NEXUS_CFG_DIR", r"C:\Quant-Nexus-Eng"))
_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{30,}$")

def _dig(d, path):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d

def load_credentials():
    tok = os.getenv("TG_TOKEN", "")
    chat = os.getenv("TG_CHAT_ID", "")
    if not (tok and chat):
        for name in ("master_telegram_trio.json", "cadence_anchor.json"):
            target = CFG_DIR / name
            if not target.exists(): continue
            try:
                cfg = json.loads(target.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError): continue
            if not tok:
                for k in ("quant_alert_bot.token", "cadence_bot.token", "bots.cadence.token", "nexus_ai_bot.token", "token", "bot_token"):
                    v = _dig(cfg, k)
                    if v and _TOKEN_RE.match(str(v)):
                        tok = str(v)
                        break
            if not chat:
                for k in ("chat_id", "quant_alert_bot.chat_id", "bots.cadence.chat_id", "nexus_ai_bot.chat_id"):
                    v = _dig(cfg, k)
                    if v:
                        chat = str(v)
                        break
    if not _TOKEN_RE.match(tok):
        sys.exit("No valid TG_TOKEN found in environment or configuration files.")
    if not re.match(r"^-?\d+$", str(chat)):
        sys.exit("No valid TG_CHAT_ID found in environment or configuration files.")
    return tok, int(chat)

TOKEN, CHAT_ID = load_credentials()
SUFFIX = os.environ.get("SYMBOL_SUFFIX", "")
FLEET = [("BTCUSD", "M15"), ("XAUUSD", "M5"), ("EURUSD", "M15"),
         ("GBPUSD", "M15"), ("USDJPY", "M5"), ("GBPJPY", "M15")]
TF_MIN = {"M5": 5, "M15": 15}
CADENCE, MAX_FLEET = 60.0, 4
CB_DRAWDOWN = float(os.environ.get("CB_DRAWDOWN", "100"))
RISK_FIXED_MAX = 15.00
AUTO_EXECUTE = os.environ.get("AUTO_EXECUTE", "1") == "1"
MAX_SPREAD_FRAC, MARGIN_USE_CAP = 0.20, 0.60
MAGIC = 750075
TARGET_MT5_PATH = r"C:\MT5_Quant_278017866\terminal64.exe"

MIN_TRADES, MIN_SAMPLE, QUOTE_Z_DAMP, Z_DIR_MIN = 15, 10, 0.5, 0.75
MAX_TICKS = 200_000
ANCHOR_FILE, STATE_FILE, LOG_FILE = "cadence_anchor.json", "qip_state.json", "quantum_institutional_pro.log"
LOCK_PORT, MT5_SNAPSHOT_TIMEOUT = 48212, 8.0
GLOBES = ['🌍', '🌎', '🌏', '🌐']
SEP = "\u2501" * 28

log = logging.getLogger("qip")
log.setLevel(logging.INFO)
_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
for _h in (RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"), logging.StreamHandler()):
    _h.setFormatter(_fmt); log.addHandler(_h)
for _n in ("httpx", "httpcore"): logging.getLogger(_n).setLevel(logging.WARNING)

CCY = {"USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD","SEK","NOK","DKK","PLN","MXN","ZAR","SGD","HKD","TRY","CNH","CZK","HUF"}
METALS = {"XAU","XAG","XPT","XPD"}
ENERGY = {"XTI","XBR","XNG","USOIL","UKOIL"}
CRYPTO = {"BTC","ETH","LTC","XRP","SOL","BNB","ADA","DOGE","DOT","LINK","BCH"}
INDICES = {"US30","US500","SPX500","NAS100","USTEC","US100","GER40","DE40","DAX40","UK100","JP225","FRA40","EU50","AUS200","HK50"}

def classify(sym):
    s = sym.upper()
    if s in INDICES: return "INDEX", s, None
    if len(s) >= 6 and s[-3:] in CCY:
        b, q = s[:-3], s[-3:]
        if b in CCY: return "FX", b, q
        if b in METALS: return "METAL", b, q
        if b in ENERGY: return "ENERGY", b, q
        if b in CRYPTO: return "CRYPTO", b, q
    return "OTHER", s, None

def norm_sym(raw):
    s = raw.upper()
    if SUFFIX and s.endswith(SUFFIX.upper()): s = s[:-len(SUFFIX)]
    if classify(s)[0] == "OTHER":
        for b, _ in FLEET:
            if s.startswith(b): return b
    return s

def legs(sym, side):
    sg = 1 if side in ("BUY", "LONG") else -1
    cls, b, q = classify(sym)
    if cls == "INDEX": return {"IDX": sg}
    if q: return {b: sg, q: -sg}
    return {b: sg}

def corr_check(sym, side, held):
    cnt = Counter()
    for p in held:
        for leg, sg in legs(p["sym"], p["side"]).items(): cnt[(leg, sg)] += 1
    for leg, sg in legs(sym, side).items():
        lim = 1 if leg == "IDX" else 2 if leg == "USD" else 1
        if cnt[(leg, sg)] >= lim: return f"{'+' if sg > 0 else '-'}{leg} limit ({lim})"
    return None

def get_market_session_compact():
    now = datetime.now(timezone.utc)
    t_min = now.hour * 60 + now.minute
    if 420 <= t_min < 960:
        sess = "\U0001F1EC\U0001F1E7 LDN-NY" if 720 <= t_min < 960 else "\U0001F1EC\U0001F1E7 LDN"
    elif 720 <= t_min < 1260:
        sess = "\U0001F1FA\U0001F1F8 NY"
    elif t_min >= 1320 or t_min < 480:
        sess = "\U0001F1EF\U0001F1F5 ASIA"
    else:
        sess = "\U0001F310 OFF-FLOW"
    targets = [(420, "LDN"), (720, "NY"), (1380, "ASIA")]
    next_s = ""
    for target_min, label in targets:
        diff = target_min - t_min
        if diff > 0:
            next_s = f"{label} -{diff//60}h{diff%60:02d}m"
            break
    if not next_s:
        diff = (420 + 1440) - t_min
        next_s = f"LDN -{diff//60}h{diff%60:02d}m"
    return f"{sess} ({next_s})"

@dataclass
class State:
    gate: int = 75
    flatten_armed_until: float = 0.0
    flatten_req: bool = False
    last_snap: dict | None = None
    day: str = ""
    hwm: float = 0.0
    cb_latched: bool = False
    frame_idx: int = 0

S = State()
REFRESH_EVENT: asyncio.Event
mt5_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5")

def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f)
    os.replace(tmp, path)

async def mt5_call(fn, *a, timeout=20.0):
    return await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(mt5_pool, fn, *a), timeout)

class TGError(Exception):
    def __init__(self, code, desc, retry_after=0.0):
        super().__init__(f"{code} {desc}"); self.code, self.desc, self.retry_after = code, desc, float(retry_after)

class Telegram:
    def __init__(self, token):
        base = f"https://api.telegram.org/bot{token}"
        lim = lambda n: httpx.Limits(max_connections=n, max_keepalive_connections=n, keepalive_expiry=120)
        self.out = httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(8.0, connect=3.05), limits=lim(4))
        self.poll = httpx.AsyncClient(base_url=base, timeout=httpx.Timeout(45.0, connect=5.0), limits=lim(1))
        self.block_until, self.streak = 0.0, 0

    def blocked_for(self): return max(0.0, self.block_until - time.monotonic())

    async def call(self, method, payload, *, poll=False):
        wait = self.blocked_for()
        if wait > 0: raise TGError(429, "rate-limit cooldown", wait)
        try: r = await (self.poll if poll else self.out).post(f"/{method}", json=payload)
        except httpx.HTTPError as e: raise TGError(0, f"network {type(e).__name__}")
        try: j = r.json()
        except ValueError: raise TGError(r.status_code, "non-JSON response")
        if j.get("ok"): self.streak = 0; return j["result"]
        code, desc = j.get("error_code"), j.get("description", "")
        if code == 429:
            ra = float(j.get("parameters", {}).get("retry_after", 1))
            delay = min(ra * (2 ** self.streak), 300.0); self.streak = min(self.streak + 1, 6)
            self.block_until = time.monotonic() + delay
            log.warning("HTTP 429 - backing off %.1fs", delay)
            raise TGError(429, desc, delay)
        raise TGError(code, desc)

    async def aclose(self): await self.out.aclose(); await self.poll.aclose()

T: Telegram

def keyboard(gate):
    a = lambda g: f"\U0001F3AF Gate {g}%" + (" \u25CF" if gate == g else "")
    return {"inline_keyboard": [
        [{"text": "\U0001F4CA /status", "callback_data": "cmd_status"},
         {"text": "\U0001F4E1 /scan", "callback_data": "cmd_scan"}],
        [{"text": a(75), "callback_data": "set_gate_75"},
         {"text": a(80), "callback_data": "set_gate_80"},
         {"text": "\U0001F6A8 /flatten", "callback_data": "cmd_flatten"}]]}

class Anchor:
    def __init__(self):
        self.mid = None
        try:
            d = json.load(open(ANCHOR_FILE, encoding="utf-8"))
            if d.get("chat_id") == CHAT_ID: self.mid = d.get("message_id")
        except Exception: pass

    async def push(self, text, kb):
        base = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": kb}
        if self.mid:
            try:
                await T.call("editMessageText", {**base, "message_id": self.mid}); return "edited"
            except TGError as e:
                d = e.desc.lower()
                if "not modified" in d: return "same"
                if e.code == 429: return "ratelimited"
                if not any(s in d for s in ("not found", "can't be edited", "message_id_invalid")): raise
        m = await T.call("sendMessage", base)
        self.mid = m["message_id"]
        await asyncio.to_thread(_atomic_json, ANCHOR_FILE, {"chat_id": CHAT_ID, "message_id": self.mid})
        return "sent"

def ffill_nonzero(a):
    idx = np.where(a != 0, np.arange(len(a)), 0)
    np.maximum.accumulate(idx, out=idx)
    return a[idx]

def classify_ticks(t):
    n = len(t)
    if n < 2: return None
    fl = t["flags"].astype(np.int64)
    bid, ask, last = t["bid"].astype(float), t["ask"].astype(float), t["last"].astype(float)
    vr = t["volume_real"].astype(float) if "volume_real" in t.dtype.names else np.zeros(n)
    v = np.where(vr > 0, vr, t["volume"].astype(float))
    trade = ((fl & (8 | 32 | 64)) > 0) & (last > 0)
    if int(trade.sum()) >= MIN_TRADES:
        ix = np.flatnonzero(trade)
        lp, bi, aa, f, w = last[ix], bid[ix], ask[ix], fl[ix], np.where(v[ix] > 0, v[ix], 1.0)
        side = np.zeros(len(ix))
        side[((f & 32) > 0) & ((f & 64) == 0)] = 1
        side[((f & 64) > 0) & ((f & 32) == 0)] = -1
        rest = side == 0
        side[rest & (aa > 0) & (lp >= aa)] = 1
        side[rest & (bi > 0) & (lp <= bi)] = -1
        rem = side == 0
        if rem.any(): side[rem] = ffill_nonzero(np.sign(np.diff(lp, prepend=lp[0])))[rem]
        mode, damp = "TAPE", 1.0
    else:
        d = np.sign(np.diff((bid + ask) / 2.0)); side = d[d != 0]
        w = np.ones(len(side)); mode, damp = "QUOTE", QUOTE_Z_DAMP
    if len(side) < MIN_SAMPLE: return None
    buy, sell = float(w[side > 0].sum()), float(w[side < 0].sum())
    tot = buy + sell
    if tot <= 0: return None
    delta = buy - sell
    return dict(delta=delta, dii=delta / tot, z=damp * delta / math.sqrt(float((w ** 2).sum())), mode=mode)

def edge_model(fm, fo):
    if fm is None or fo is None: return 50.0, "FLAT", 0.0
    zc = 0.65 * fm["z"] + 0.35 * fo["z"]
    if fm["z"] * fo["z"] < 0 and min(abs(fm["z"]), abs(fo["z"])) >= 1.0: return 50.0, "FLAT", zc
    edge = min(99.0, 50.0 + 50.0 * math.tanh(abs(zc) / 3.5))
    return edge, ("BUY" if zc >= Z_DIR_MIN else "SELL" if zc <= -Z_DIR_MIN else "FLAT"), zc

def ensure_mt5():
    acc = mt5.account_info()
    if acc is not None and acc.login == 278017866:
        return
    mt5.shutdown()
    if not mt5.initialize(path=TARGET_MT5_PATH):
        raise RuntimeError(f"mt5.initialize failed on {TARGET_MT5_PATH}: {mt5.last_error()}")
    acc = mt5.account_info()
    if acc is None or acc.login != 278017866:
        raise RuntimeError(f"MT5 bound to wrong account ({getattr(acc, 'login', None)} != 278017866)")

def fetch_ticks(sym, end_epoch, window_sec):
    end_epoch, start = int(end_epoch), int(end_epoch) - int(window_sec)
    t = mt5.copy_ticks_from(sym, start, MAX_TICKS, mt5.COPY_TICKS_ALL)
    if t is None or len(t) == 0:
        t = mt5.copy_ticks_range(sym, datetime.fromtimestamp(start, timezone.utc), datetime.fromtimestamp(end_epoch + 1, timezone.utc), mt5.COPY_TICKS_ALL)
    if t is None or len(t) == 0: return None
    t = t[t["time"] <= end_epoch + 1]
    return t if len(t) else None

def flow(sym, minutes, end_epoch):
    t = fetch_ticks(sym, end_epoch, minutes * 60)
    return None if t is None else classify_ticks(t)

def atr15(sym, n=14):
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, n + 1)
    if r is None or len(r) < n + 1: return 0.0
    h, l, pc = r["high"][1:], r["low"][1:], r["close"][:-1]
    return float(np.mean(np.maximum.reduce([h - l, np.abs(h - pc), np.abs(l - pc)])))

def size_lots(info, acc, otype, sym, entry, sl):
    vmin, vmax, step = info.volume_min, info.volume_max, (info.volume_step or 0.01)
    probe = min(max(1.0, vmin), vmax)
    pl = mt5.order_calc_profit(otype, sym, probe, entry, sl)
    loss1 = abs(pl) / probe if (pl is not None and pl != 0) else (abs(entry - sl) / info.trade_tick_size * info.trade_tick_value if info.trade_tick_size else 0)
    if loss1 <= 0: return 0.0, 0.0
    budget = min(acc.equity * 0.01, RISK_FIXED_MAX)
    lots = min(max(math.floor(budget / loss1 / step + 1e-9) * step, vmin), vmax)
    if lots * loss1 > 2 * budget: return 0.0, 0.0
    return round(lots, 8), round(lots * loss1, 2)

def collect_snapshot(gate):
    ensure_mt5()
    acc = mt5.account_info()
    if acc is None: raise RuntimeError("account_info None")
    now = datetime.now(timezone.utc); today = now.strftime("%Y-%m-%d")
    if S.day != today: S.day, S.hwm, S.cb_latched = today, acc.equity, False
    if acc.equity > S.hwm: S.hwm = acc.equity
    buffer = CB_DRAWDOWN - (S.hwm - acc.equity)
    if buffer <= 0 and not S.cb_latched: S.cb_latched = True
    cb = S.cb_latched

    pos = []
    for p in (mt5.positions_get() or []):
        info = mt5.symbol_info(p.symbol)
        pos.append(dict(ticket=p.ticket, symbol=norm_sym(p.symbol), side="BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                        volume=p.volume, floating_pnl=p.profit + p.swap, entry_price=p.price_open, digits=getattr(info, "digits", 2)))
    held = {p["symbol"] for p in pos}

    ticks = {}
    for base, _ in FLEET:
        mt5.symbol_select(base + SUFFIX, True)
        ticks[base] = mt5.symbol_info_tick(base + SUFFIX)

    rows = []
    for base, tf in FLEET:
        tk, other = ticks[base], ("M5" if tf == "M15" else "M15")
        if tk is None:
            rows.append(dict(sym=base, tf=tf, bias="FLAT", edge=50.0, delta=0.0, dii=0.0, in_trade=base in held)); continue
        fm, fo = flow(base + SUFFIX, TF_MIN[tf], tk.time), flow(base + SUFFIX, TF_MIN[other], tk.time)
        edge, direction, _ = edge_model(fm, fo)
        rows.append(dict(sym=base, tf=tf, bias=direction, edge=edge, delta=fm["delta"] if fm else 0.0, dii=fm["dii"] if fm else 0.0, in_trade=base in held))

    triggers = []
    if not cb and len(held) < MAX_FLEET:
        for r in sorted([r for r in rows if r["edge"] >= gate and r["bias"] != "FLAT" and not r["in_trade"]], key=lambda x: -x["edge"]):
            if corr_check(r["sym"], r["bias"], [{"sym": p["symbol"], "side": p["side"]} for p in pos]): continue
            sym = r["sym"] + SUFFIX; info, tk, a = mt5.symbol_info(sym), ticks[r["sym"]], atr15(sym)
            if not (info and tk and a > 0): continue
            buy = r["bias"] == "BUY"
            entry = tk.ask if buy else tk.bid
            sl_d = max(1.5 * a, 1.2 * info.trade_stops_level * info.point)
            sl, tp = (entry - sl_d, entry + sl_d * 2.0) if buy else (entry + sl_d, entry - sl_d * 2.0)
            sl, tp = round(sl, info.digits), round(tp, info.digits)
            lots, actual_risk = size_lots(info, acc, mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL, sym, entry, sl)
            if lots <= 0: continue
            triggers.append(dict(symbol=r["sym"], bias=r["bias"], prob=r["edge"], lots=lots, risk=actual_risk, entry=entry, sl=sl, tp=tp, digits=info.digits))
            break

    return dict(nav=acc.equity, float=acc.profit, free=acc.margin_free, buffer=buffer, cb=cb,
                pos=pos, fleet_locked=len(held), total_fleet=len(FLEET), rows=rows, triggers=triggers, gate=gate)

def fl(x): return f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"




async def position_watcher():
    last_tickets = frozenset()
    while True:
        try:
            cur = frozenset(p.ticket for p in (await mt5_call(mt5.positions_get, timeout=5.0) or []))
            if cur != last_tickets:
                last_tickets = cur
                REFRESH_EVENT.set()
        except Exception: pass
        await asyncio.sleep(1.0)

def render_decay_frame(s, frame):
    """Simulates fine particle sand erosion and brush-stroke dispersion."""
    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    globe = GLOBES[frame % len(GLOBES)]
    sess_compact = get_market_session_compact()

    sand_card = [
        "⁖⁘⁛ <b>SHIVSOUL NEXUS // EROSION MATRIX</b> ⁛⁘⁖",
        "⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘",
        "<code>NAV   $⁖,⁘⁛.·⁞  | Float ⁘·⁖.⁛⁞</code>",
        "<code>FreeM $⁖,⁘⁛.·⁞  | Fleet ⁘/6</code>",
        "<code>OMEGA-APEX-v2.0  | ⁖⁘ PARTICLE DISPERSION ⁘⁖</code>",
        "⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘",
        "⚡ <b>LIVE EXECUTIONS: [SAND-BRUSH FLUSHING]</b>",
        "<code>⁖⁘⁛·⁞⁖ • ⁘⁘⁘⁘ 0.00L | Open ⁖⁘⁛.·⁞⁖</code>",
        "⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘",
        "🎯 <b>ALPHA TRIGGER:</b> <code>[PULSE RE-INDEXING]</code>",
        "⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘",
        "📡 <b>MICROSTRUCTURE SCANNER (BURST RESOLVING)</b>",
        "<code>#1 ⁖⁘⁛·⁞⁖ ⚪ ⁘⁘⁘⁘ [⁖⁘⁛] ⁘⁖% | Δ:⁘·⁖⁛⁞ DII:⁘·⁖⁛</code>",
        "<code>#2 ⁖⁘⁛·⁞⁖ ⚪ ⁘⁘⁘⁘ [⁖⁘⁛] ⁘⁖% | Δ:⁘·⁖⁛⁞ DII:⁘·⁖⁛</code>",
        "<code>#3 ⁖⁘⁛·⁞⁖ ⚪ ⁘⁘⁘⁘ [⁖⁘⁛] ⁘⁖% | Δ:⁘·⁖⁛⁞ DII:⁘·⁖⁛</code>",
        "<code>#4 ⁖⁘⁛·⁞⁖ ⚪ ⁘⁘⁘⁘ [⁖⁘⁛] ⁘⁖% | Δ:⁘·⁖⁛⁞ DII:⁘·⁖⁛</code>",
        "<code>#5 ⁖⁘⁛·⁞⁖ ⚪ ⁘⁘⁘⁘ [⁖⁘⁛] ⁘⁖% | Δ:⁘·⁖⁛⁞ DII:⁘·⁖⁛</code>",
        "<code>#6 ⁖⁘⁛·⁞⁖ ⚪ ⁘⁘⁘⁘ [⁖⁘⁛] ⁘⁖% | Δ:⁘·⁖⁛⁞ DII:⁘·⁖⁛</code>",
        "⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘⁘",
        f"{globe} <b>BURSTING MATRIX // INSTANTIATING PULSE...</b>",
        f"⏱️ <i>{now_utc}</i> | <code>{sess_compact}</code> | <code>⁖⁘%</code>"
    ]
    return chr(10).join(sand_card)


def render_dashboard(s, frame):
    now_utc = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
    globe = GLOBES[frame % len(GLOBES)]
    sess_compact = get_market_session_compact()
    out = [
        '🔱 <b>SHIVSOUL NEXUS / OMEGA APEX ELITE MATRIX</b>',
        SEP,
        f"<code>NAV   ${s['nav']:,.2f}</code>",
        f"<code>Float {fl(s['float'])}</code>",
        f"<code>FreeM ${s['free']:,.2f} | Fleet {s['fleet_locked']}/{s['total_fleet']}</code>",
        '<code>OMEGA-APEX-v2.0 | 100% AUTONOMOUS</code>',
        SEP
    ]
    if not s['pos']:
        out.append('⚡ <b>ACTIVE POSITIONS (CORRELATION SHIELD)</b>')
        out.append('• <i>Zero directional exposure — All engines flat</i>')
        out.append(SEP)
    else:
        out.append('⚡ <b>LIVE MARKET EXECUTIONS (LOCKED)</b>')
        for p_item in s['pos']:
            d = p_item.get('digits', 2)
            sym = str(p_item.get('symbol', '')).strip()
            side = str(p_item.get('side', '')).strip()
            vol = float(p_item.get('volume', 0.0))
            pnl = fl(p_item.get('floating_pnl', 0.0))
            op_p = f"{p_item.get('entry_price', 0.0):,.{d}f}"
            out.append(f'<u><b>{sym}</b> • {side} {vol:.2f}L</u>')
            out.append(f'<u>Float {pnl} | Open {op_p}</u>')
        out.append(SEP)
    trig = s.get('trigger') or s.get('top_trigger')
    if trig:
        t = trig
        edge_val = int(round(float(t.get('edge', 0))))
        out.append(f"🎯 <b>ALPHA TRIGGER: {t['sym']} ({t['dir']} @ {edge_val}%)</b>")
        out.append(f"\u2022 <i>Order Sizing:</i> <code>{t['lots']:.2f} Lots (${t['risk_usd']:.2f} risk)</code>")
        out.append(f"\u2022 <i>Entry:</i> <code>${t['entry']:,.2f}</code>")
        out.append(f"\u2022 <i>SL:</i> <code>${t['sl']:,.2f}</code> | <i>TP:</i> <code>${t['tp']:,.2f}</code>")
        out.append(SEP)
    else:
        out.append('🎯 <b>ALPHA TRIGGER:</b> <code>Matrix Balanced | Awaiting Edge</code>')
        out.append(SEP)
    out.append('📡 <b>MICROSTRUCTURE SCANNER FLEET (M15+M5 DUAL)</b>')
    for i, r in enumerate(s['rows'], 1):
        c = '🟢' if r.get('bias') == 'LONG' else ('🔴' if r.get('bias') == 'SHRT' else '⚪')
        tag = '🔒 [LCK]' if r.get('in_trade') else '⚡ [HUNT]'
        dii_str = f"{float(r.get('dii', 0.0)):+.2f}"
        delta_val = int(round(float(r.get('delta', 0))))
        delta_str = f"{delta_val:+d}"
        edge_int = int(round(float(r.get('edge', 0))))
        sym = str(r.get('sym', ''))[:6]
        tf = str(r.get('tf', 'M15'))[:3]
        bias = str(r.get('bias', 'FLAT'))[:4]
        row_l1 = f"#{i} {sym:<6} {c} {bias:<4} [{tf:<3}] {edge_int:>2}%"
        row_l2 = f"   Δ:{delta_str:>5} DII:{dii_str:>5} {tag}"
        out.append(f'<code>{row_l1}</code>')
        out.append(f'<code>{row_l2}</code>')
    out.append(SEP)
    out.append(f'{globe} <b>LIVE 60S CADENCE ACTIVE</b>')
    out.append(f'⏱️ <i>{now_utc}</i> | <code>{sess_compact}</code> | <code>{s["gate"]}%</code>')
    return chr(10).join(out)


async def cadence():
    anchor = Anchor()
    next_tick = asyncio.get_running_loop().time()
    while True:
        now_time = asyncio.get_running_loop().time()
        left = next_tick - now_time
        if left <= 0 or REFRESH_EVENT.is_set():
            REFRESH_EVENT.clear()
            S.frame_idx += 1
            next_tick = asyncio.get_running_loop().time() + CADENCE
            try:
                # Visual Character Fade-Away (keeps decimals and skeleton intact)
                if S.last_snap:
                    fade_text = render_decay_frame(S.last_snap, S.frame_idx)
                    await anchor.push(fade_text, keyboard(S.gate))
                    await asyncio.sleep(0.65)

                # Manifest fresh 60s frame
                snap = await mt5_call(collect_snapshot, S.gate)
                S.last_snap = snap
                text = render_dashboard(snap, S.frame_idx)
                res = await anchor.push(text, keyboard(S.gate))
                log.info("Cadence text-fade complete (%s, Frame %d)", res, S.frame_idx % len(GLOBES))
            except Exception as e:
                log.warning("Cadence cycle exception: %s", e)
        else:
            try:
                await asyncio.wait_for(REFRESH_EVENT.wait(), timeout=max(0.2, min(left, 1.0)))
            except asyncio.TimeoutError:
                pass

async def interaction():
    offset = None
    while True:
        try:
            ups = await T.call("getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": ["callback_query", "message"]}, poll=True)
        except TGError as e:
            await asyncio.sleep(max(3.0, e.retry_after)); continue
        for u in ups:
            offset = u["update_id"] + 1
            cq = u.get("callback_query")
            if not cq: continue
            data = cq.get("data", "")
            ans = "OK"
            if data == "cmd_status":
                ans = f"NAV: ${S.last_snap['nav']:,.2f} | Gate: {S.gate}%" if S.last_snap else "Initializing..."
            elif data == "cmd_scan":
                REFRESH_EVENT.set(); ans = "Scan cycle queued."
            elif data == "set_gate_75":
                S.gate = 75; REFRESH_EVENT.set(); ans = "Gate set to 75%."
            elif data == "set_gate_80":
                S.gate = 80; REFRESH_EVENT.set(); ans = "Gate set to 80%."
            elif data == "cmd_flatten":
                ans = "Flatten requires terminal arming."
            await T.call("answerCallbackQuery", {"callback_query_id": cq["id"], "text": ans})

async def main():
    global REFRESH_EVENT, T
    REFRESH_EVENT = asyncio.Event()
    T = Telegram(TOKEN)
    try: await T.call("deleteWebhook", {})
    except Exception: pass
    log.info("Starting ShivSoul Nexus Pro on anchor...")
    try:
        await asyncio.gather(cadence(), interaction(), position_watcher())
    finally:
        await T.aclose()

if __name__ == "__main__":
    guard = socket.socket()
    try: guard.bind(("127.0.0.1", LOCK_PORT))
    except OSError: sys.exit("Instance lock active on port 48212. Single-writer guard engaged.")
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
    finally: mt5.shutdown()