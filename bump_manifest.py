# -*- coding: utf-8 -*-
"""Пишет version.json для указанной версии: ссылки на оба установщика из Release + заметки из NOTES.md."""
import datetime
import json
import sys

ver = sys.argv[1].lstrip("v")
try:
    notes = open("NOTES.md", encoding="utf-8").read().strip()
except FileNotFoundError:
    notes = ""
base = f"https://github.com/alegawhats-del/StampStudio/releases/download/v{ver}"
data = {
    "version": ver,
    "date": datetime.date.today().isoformat(),
    "notes": notes,
    "setup": f"{base}/StampStudio-Setup-{ver}.exe",
    "setup_canon": f"{base}/StampStudioCanon-Setup-{ver}.exe",
}
with open("version.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(json.dumps(data, ensure_ascii=False, indent=2))
