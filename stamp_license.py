# -*- coding: utf-8 -*-
"""Лицензия программы через KeyAuth (keyauth.cc). Без Qt.

Ключ проверяется на сервере и привязывается к компьютеру. Ответ сервера подписан
(Ed25519) — подпись проверяется, чтобы ответ нельзя было подделать по дороге.
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

APP_NAME = "Eagles"
OWNER_ID = "IJoPRCSjQ0"
APP_VER = "1.0"
URL = "https://keyauth.win/api/1.3/"
PUBKEY = "5586b4bc69c7a4b487e4563a4cd96afd39140f919bd31cea7d1c6a1e8439422b"
TELEGRAM = "https://t.me/chebyrashka_dev"
TELEGRAM_NAME = "@chebyrashka_dev"
GRACE = 3 * 24 * 3600            # сколько можно работать без связи с сервером после удачной проверки
CLOCK_SLACK = 24 * 3600          # на сколько могут расходиться часы компьютера и сервера

# ---------------------------------------------------------------- Ed25519 (только проверка подписи)

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _xrecover(_BY)
_B = (_BX, _BY, 1, _BX * _BY % _P)


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % _P
    B = (y1 + x1) * (y2 + x2) % _P
    C = t1 * 2 * _D * t2 % _P
    Dd = z1 * 2 * z2 % _P
    E, F, G, H = B - A, Dd - C, Dd + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _mul(s, pt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, pt)
        pt = _add(pt, pt)
        s >>= 1
    return q


def _decode_point(b):
    y = int.from_bytes(b, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        raise ValueError("point")
    x = _xrecover(y)
    if (x * x - (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)) % _P != 0:
        raise ValueError("point")
    if (x & 1) != sign:
        x = _P - x
    return (x, y, 1, x * y % _P)


def _eq(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def ed25519_verify(public_hex, message: bytes, signature_hex) -> bool:
    try:
        pk = bytes.fromhex(public_hex)
        sig = bytes.fromhex(signature_hex)
        if len(pk) != 32 or len(sig) != 64:
            return False
        A = _decode_point(pk)
        R = _decode_point(sig[:32])
        S = int.from_bytes(sig[32:], "little")
        if S >= _L:
            return False
        h = int.from_bytes(hashlib.sha512(sig[:32] + pk + message).digest(), "little") % _L
        return _eq(_mul(S, _B), _add(R, _mul(h, A)))
    except Exception:
        return False


# ---------------------------------------------------------------- компьютер и файл программы

def hwid() -> str:
    """Метка компьютера, к которой сервер привязывает ключ."""
    if sys.platform == "win32":
        try:
            import win32security
            sid = win32security.LookupAccountName(None, os.getlogin())[0]
            return win32security.ConvertSidToStringSid(sid)
        except Exception:
            pass
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return "MG-" + str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except Exception:
            pass
    try:
        with open("/etc/machine-id") as f:
            return f.read().strip()
    except Exception:
        import platform
        return "PC-" + hashlib.sha1((platform.node() + os.path.expanduser("~")).encode()).hexdigest()[:24]


def checksum() -> str:
    """MD5 файла программы (сервер может сверять его, если это включено в кабинете KeyAuth)."""
    try:
        if getattr(sys, "frozen", False):
            h = hashlib.md5()
            with open(sys.executable, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------- запросы к серверу

class NetError(Exception):
    """Сервер лицензий недоступен (нет интернета, блокировка, сбой)."""


def _http(data: dict, timeout=12):
    """POST → (текст ответа, заголовки). Подменяется в тестах."""
    req = urllib.request.Request(URL, data=urllib.parse.urlencode(data).encode(),
                                 headers={"User-Agent": "StampStudio"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace"), {k.lower(): v for k, v in r.headers.items()}


def _request(data: dict) -> dict:
    try:
        body, headers = _http(data)
    except Exception as e:
        raise NetError(str(e))
    if body.strip() == "KeyAuth_Invalid":
        return {"success": False, "message": "KeyAuth_Invalid"}
    sig, ts = headers.get("x-signature-ed25519"), headers.get("x-signature-timestamp")
    if not sig or not ts:
        raise NetError("ответ сервера без подписи")
    if not ed25519_verify(PUBKEY, str(ts).encode() + body.encode("utf-8"), sig):
        raise NetError("подпись ответа сервера не сошлась")
    try:
        if abs(time.time() - int(ts)) > CLOCK_SLACK:
            raise NetError("ответ сервера устарел — проверьте дату и время на компьютере")
    except ValueError:
        raise NetError("ответ сервера без времени")
    try:
        return json.loads(body)
    except Exception:
        raise NetError("сервер ответил непонятно")


MESSAGES = [                       # что ответил сервер → как сказать человеку
    ("key not found", "Такого ключа нет. Проверьте, что ключ введён полностью и без пробелов."),
    ("invalid license", "Такого ключа нет. Проверьте, что ключ введён полностью и без пробелов."),
    ("hwid doesn", "Ключ уже привязан к другому компьютеру. Напишите в Telegram — ключ перенесут."),
    ("already used", "Ключ уже активирован на другом компьютере. Напишите в Telegram — ключ перенесут."),
    ("expired", "Срок действия ключа закончился. Напишите в Telegram, чтобы продлить."),
    ("no active subscription", "Срок действия ключа закончился. Напишите в Telegram, чтобы продлить."),
    ("banned", "Ключ заблокирован. Напишите в Telegram."),
    ("blacklist", "Этот компьютер заблокирован. Напишите в Telegram."),
    ("paused", "Ключ приостановлен. Напишите в Telegram."),
    ("disabled", "Проверка лицензий временно отключена. Попробуйте позже или напишите в Telegram."),
    ("session", "Сервер не принял запрос. Попробуйте ещё раз."),
    ("keyauth_invalid", "Программа не зарегистрирована на сервере лицензий. Напишите в Telegram."),
    ("hash", "Эта сборка программы не подходит. Установите свежую версию или напишите в Telegram."),
]


def explain(message: str) -> str:
    m = str(message or "").lower()
    for part, text in MESSAGES:
        if part in m:
            return text
    return f"Сервер лицензий ответил: {message}" if message else "Ключ не принят."


def check(key: str) -> dict:
    """Проверить ключ на сервере.

    Возвращает {ok, message, expiry, level, net, update}:
      ok — ключ принят; net — True, если сервер недоступен (это не отказ);
      update — ссылка на новую версию, если сервер требует обновиться."""
    key = str(key or "").strip()
    if not key:
        return {"ok": False, "message": "Введите ключ.", "net": False}
    try:
        init = _request({"type": "init", "ver": APP_VER, "hash": checksum(), "name": APP_NAME, "ownerid": OWNER_ID})
        if str(init.get("message")) == "invalidver":
            return {"ok": False, "net": False, "update": str(init.get("download") or ""),
                    "message": "Нужна новая версия программы. Установите обновление."}
        if not init.get("success"):
            return {"ok": False, "net": False, "message": explain(init.get("message"))}
        ans = _request({"type": "license", "key": key, "hwid": hwid(), "sessionid": init.get("sessionid", ""),
                        "name": APP_NAME, "ownerid": OWNER_ID})
    except NetError as e:
        return {"ok": False, "net": True,
                "message": f"Нет связи с сервером лицензий ({e}). Проверьте интернет и попробуйте ещё раз."}
    if not ans.get("success"):
        return {"ok": False, "net": False, "message": explain(ans.get("message"))}
    subs = ((ans.get("info") or {}).get("subscriptions") or [])
    expiry = 0
    for s in subs:
        try:
            expiry = max(expiry, int(s.get("expiry") or 0))
        except Exception:
            continue
    level = str(subs[0].get("subscription") or "") if subs else ""
    return {"ok": True, "net": False, "message": "Ключ принят.", "expiry": expiry, "level": level}


# ---------------------------------------------------------------- запомненная лицензия

def _seal(key, ok_ts, expiry):
    raw = f"{key}|{int(ok_ts)}|{int(expiry)}|{hwid()}|stampstudio-license"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def remember(key, expiry, protect) -> dict:
    """Запись для настроек после удачной проверки. protect — шифрование ключа (DPAPI)."""
    now = int(time.time())
    return {"key": protect(key), "ok_ts": now, "expiry": int(expiry or 0), "seal": _seal(key, now, expiry or 0)}


def cached(rec, unprotect):
    """Что запомнено: (ключ, годится ли без проверки на сервере, срок). Ключа нет — ('', False, 0)."""
    try:
        key = unprotect((rec or {}).get("key") or "")
    except Exception:
        key = ""
    if not key:
        return "", False, 0
    ok_ts, expiry = int(rec.get("ok_ts") or 0), int(rec.get("expiry") or 0)
    now = time.time()
    fresh = (rec.get("seal") == _seal(key, ok_ts, expiry) and ok_ts <= now + 600
             and now - ok_ts < GRACE and (not expiry or now < expiry))
    return key, fresh, expiry


def expiry_text(expiry) -> str:
    try:
        e = int(expiry or 0)
    except Exception:
        e = 0
    if not e:
        return "без срока"
    if e - time.time() > 20 * 365 * 24 * 3600:
        return "бессрочно"
    return "до " + time.strftime("%d.%m.%Y", time.localtime(e))


def mask(key: str) -> str:
    k = str(key or "")
    return k if len(k) <= 8 else k[:4] + "…" + k[-4:]


# ---------------------------------------------------------------- самопроверка

def selftest():
    # подпись: контрольный пример из RFC 8032 (раздел 7.1, TEST 2)
    pk = "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
    sg = ("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
          "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")
    assert ed25519_verify(pk, b"\x72", sg) and not ed25519_verify(pk, b"\x73", sg)
    assert not ed25519_verify(pk, b"\x72", sg[:-2] + "01") and not ed25519_verify("zz", b"", "")
    assert len(hwid()) >= 6 and hwid() == hwid()
    rec = remember("KEY-123", int(time.time()) + 1000, lambda s: "p:" + s)
    un = lambda s: s[2:] if s.startswith("p:") else ""
    assert cached(rec, un) == ("KEY-123", True, rec["expiry"])
    assert cached(dict(rec, expiry=rec["expiry"] + 5), un)[1] is False            # правка срока руками не проходит
    assert cached(dict(rec, ok_ts=rec["ok_ts"] - GRACE - 5), un)[1] is False
    assert cached({}, un) == ("", False, 0)
    assert "другому компьютеру" in explain("HWID Doesn't match. Ask for key reset.") and "нет" in explain("Key Not Found.")
    assert expiry_text(0) == "без срока" and expiry_text(time.time() + 86400).startswith("до ")
    assert mask("ABCD-EFGH-IJKL") == "ABCD…IJKL"
    return True
