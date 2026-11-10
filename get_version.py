# -*- coding: utf-8 -*-
"""Печатает APP_VERSION из stamp_studio.py — для конвейера сборки.
Обе редакции обязаны иметь одну и ту же версию."""
import os
import re
import sys

here = os.path.dirname(os.path.abspath(__file__))
vers = []
for name in ("stamp_studio.py", "stamp_studio_canon.py"):
    with open(os.path.join(here, name), encoding="utf-8") as f:
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
    vers.append(m.group(1) if m else "0.0.0")
if vers[0] != vers[1]:
    sys.stderr.write(f"APP_VERSION differs: {vers}\n")
    sys.exit(1)
print(vers[0])
