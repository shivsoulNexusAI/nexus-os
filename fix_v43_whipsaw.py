from pathlib import Path

p = Path(r"C:\Quant-Nexus-Eng\nexus_multi_straddle_daemon.py")
code = p.read_text(encoding="utf-8")

old_call = "if self.whipsaw and not self.whipsaw.can_trade(sym):"
new_call = """if self.whipsaw:
                allowed = True
                for fn_name in ("is_allowed", "allow_trade", "can_trade", "check"):
                    fn = getattr(self.whipsaw, fn_name, None)
                    if callable(fn):
                        res_w = fn(sym)
                        allowed = res_w[0] if isinstance(res_w, tuple) else bool(res_w)
                        break
                if not allowed:"""

assert old_call in code, "old_call not found"
code = code.replace(old_call, new_call, 1)
code = code.replace("            if self.whipsaw:\n                allowed = True", "            if self.whipsaw:\n                allowed = True")
# Fix indentation of the following continue
code = code.replace(
    "                if not allowed:\n                continue",
    "                if not allowed:\n                    continue"
)

p.write_text(code, encoding="utf-8")
print("[OK] Patched AntiWhipsawEngine adapter in nexus_multi_straddle_daemon.py")