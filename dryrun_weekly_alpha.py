import sys
import json
import runpy
import urllib.request
from pathlib import Path

sys.path.insert(0, r"C:\Quant-Nexus-Eng")

captured_messages = []

# Intercept standard urllib Telegram POST calls during dry-run
_orig_urlopen = urllib.request.urlopen

class _DummyResponse:
    def __init__(self, body=b'{"ok":true,"result":{"message_id":0}}'):
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

def _mock_urlopen(req, *args, **kwargs):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if "api.telegram.org" in url:
        data = getattr(req, "data", None)
        if data:
            try:
                payload = json.loads(data.decode("utf-8"))
                captured_messages.append(payload.get("text", str(payload)))
            except Exception:
                captured_messages.append(data.decode("utf-8", errors="replace"))
        return _DummyResponse()
    return _orig_urlopen(req, *args, **kwargs)

urllib.request.urlopen = _mock_urlopen

# Also intercept httpx if used
try:
    import httpx
    _orig_httpx_post = httpx.post
    def _mock_httpx_post(url, *args, **kwargs):
        if "api.telegram.org" in str(url):
            json_body = kwargs.get("json") or kwargs.get("data") or {}
            captured_messages.append(json_body.get("text", str(json_body)) if isinstance(json_body, dict) else str(json_body))
            class _FakeHttpxResp:
                status_code = 200
                text = '{"ok":true}'
                def json(self): return {"ok": True}
            return _FakeHttpxResp()
        return _orig_httpx_post(url, *args, **kwargs)
    httpx.post = _mock_httpx_post
except Exception:
    pass

target = Path(r"C:\Quant-Nexus-Eng\weekly_alpha_reporter.py")
if not target.exists():
    print("[-] weekly_alpha_reporter.py not found in C:\\Quant-Nexus-Eng")
    sys.exit(1)

print("=" * 96)
print("  DRY-RUN PREVIEW: weekly_alpha_reporter.py (OUTBOUND TELEGRAM INTERCEPTED)")
print("=" * 96)

try:
    runpy.run_path(str(target), run_name="__main__")
except SystemExit:
    pass
except Exception as e:
    print(f"[!] Exception during dry-run execution: {e}")

print("\n" + "=" * 96)
print(f"  CAPTURED TELEGRAM DIGEST PAYLOADS ({len(captured_messages)})")
print("=" * 96)
if captured_messages:
    for idx, msg in enumerate(captured_messages, 1):
        print(f"--- Payload #{idx} ---")
        print(msg)
else:
    print("[INFO] No Telegram POST intercepted (check stdout above for console report output).")
print("=" * 96)