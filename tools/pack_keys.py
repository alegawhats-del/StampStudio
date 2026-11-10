# -*- coding: utf-8 -*-
"""Сборка: секрет репозитория FREE_KEYS → keys.bin, который кладётся внутрь программы.

FREE_KEYS — JSON вида {"Google Gemini": "AIza...", "Groq (быстро, бесплатно)": "gsk_..."}.
Сами ключи в репозиторий не попадают: файл keys.bin создаётся только на сборочной машине."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import json

import stamp_ai

raw = (os.environ.get("FREE_KEYS") or "").strip()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "keys.bin")
if os.path.exists(out):
    os.remove(out)
if not raw:
    print("FREE_KEYS not set - building without built-in keys")
    sys.exit(0)
try:
    data = stamp_ai.pack_keys(raw)
except Exception as e:
    print(f"FREE_KEYS is not valid JSON ({type(e).__name__}) - building without built-in keys")
    sys.exit(0)
with open(out, "wb") as f:
    f.write(data)
stamp_ai.FIND_RESOURCE = lambda name: out if name == "keys.bin" else None
names = sorted(stamp_ai.builtin_keys())
unknown = [k for k in json.loads(raw) if not stamp_ai._match_provider(str(k))]
print("builtin keys injected: " + (", ".join(names) if names else "none"))
if unknown:
    print("unknown provider names skipped: " + ", ".join(unknown))
