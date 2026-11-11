# -*- coding: utf-8 -*-
"""Облако Stamp Studio: копия печатей, карточек клиентов и настроек в своей базе MongoDB (Atlas или свой сервер).

Строку подключения вводит пользователь, в программе её нет. Всё по-прежнему лежит на компьютере — облако это
копия: без сети программа работает как обычно, а изменения уходят при следующей синхронизации.
Модуль не зависит от Qt.
"""
import base64
import hashlib
import json
import sys
import time

DB_NAME = "stampstudio"
PRIVATE_KEYS = ("passport", "passport_issued", "address", "birth")
CLIENT_FACTORY = None                       # в тестах сюда подставляется mongomock


# ----------------------------------------------------------------------------- хранение строки
def protect(text):
    """Зашифровать строку средствами Windows (расшифровать сможет только этот пользователь на этом компьютере)."""
    raw = str(text or "").encode("utf-8")
    if not raw:
        return ""
    if sys.platform == "win32":
        try:
            import win32crypt
            blob = win32crypt.CryptProtectData(raw, "StampStudio", None, None, None, 0)
            return "dpapi:" + base64.b64encode(blob).decode("ascii")
        except Exception:
            pass
    return "plain:" + base64.b64encode(raw).decode("ascii")


def unprotect(stored):
    s = str(stored or "")
    try:
        if s.startswith("dpapi:"):
            import win32crypt
            return win32crypt.CryptUnprotectData(base64.b64decode(s[6:]), None, None, None, 0)[1].decode("utf-8")
        if s.startswith("plain:"):
            return base64.b64decode(s[6:]).decode("utf-8")
    except Exception:
        return ""
    return ""


def is_encrypted(stored):
    return str(stored or "").startswith("dpapi:")


def mask(uri):
    """Строка для показа на экране: пароль скрыт."""
    import re
    return re.sub(r"(://[^:/@]+:)[^@]+@", r"\1••••••@", str(uri or ""))


# ----------------------------------------------------------------------------- подключение
def connect(uri, timeout_ms=8000):
    if CLIENT_FACTORY is not None:
        return CLIENT_FACTORY(uri)
    import pymongo
    return pymongo.MongoClient(uri, serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms,
                               socketTimeoutMS=20000, appname="StampStudio")


def database(client):
    try:
        db = client.get_default_database()
        if db is not None and db.name:
            return db
    except Exception:
        pass
    return client[DB_NAME]


def explain(e):
    """Понятная причина ошибки подключения."""
    t = str(e)
    low = t.lower()
    if "authentication failed" in low or "bad auth" in low:
        return "Неверный логин или пароль пользователя базы. Проверьте их в строке подключения (в Atlas: Database Access)."
    if "dns" in low or "srv" in low or "nxdomain" in low or "name or service not known" in low or "getaddrinfo" in low:
        return ("Не найден адрес кластера. Проверьте строку (она начинается с mongodb+srv://) и интернет. "
                "Если Atlas недоступен из вашей сети — нужен VPN или прокси на роутере.")
    if "timed out" in low or "timeout" in low or "serverselectiontimeout" in low or "connection refused" in low:
        return ("База не отвечает. Чаще всего Atlas не пускает ваш IP: в Atlas откройте Network Access и добавьте адрес "
                "(или 0.0.0.0/0). Ещё причина — нет связи или кластер на паузе.")
    if "ssl" in low or "tls" in low or "certificate" in low:
        return "Не удалось установить защищённое соединение. Проверьте дату и время на компьютере и работу прокси."
    if "invalid uri" in low or "invaliduri" in low or "must begin with" in low:
        return "Строка подключения записана неверно. Скопируйте её из Atlas целиком: Connect → Drivers."
    if "not authorized" in low or "unauthorized" in low:
        return "У пользователя базы нет прав на запись. В Atlas дайте ему роль «Read and write to any database»."
    return "Не удалось подключиться: " + t[:240]


def check(uri):
    """(получилось, сообщение). Проверяет связь, логин и право записи."""
    uri = str(uri or "").strip()
    if not uri:
        return False, "Вставьте строку подключения."
    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        return False, "Строка должна начинаться с mongodb+srv:// (Atlas) или mongodb:// (свой сервер)."
    if "<password>" in uri or "<db_password>" in uri:
        return False, "В строке осталась заготовка <password> — замените её на пароль пользователя базы."
    client = None
    try:
        client = connect(uri)
        db = database(client)
        db["_check"].update_one({"_id": "ping"}, {"$set": {"t": time.time()}}, upsert=True)
        n = db["stamps"].count_documents({"deleted": {"$ne": True}})
        c = db["clients"].count_documents({"deleted": {"$ne": True}})
        return True, f"Подключение работает. В облаке сейчас: печатей и подписей — {n}, клиентов — {c}."
    except Exception as e:
        return False, explain(e)
    finally:
        try:
            if client is not None:
                client.close()
        except Exception:
            pass


# ----------------------------------------------------------------------------- синхронизация
def digest(obj):
    if isinstance(obj, (bytes, bytearray)):
        return hashlib.sha1(bytes(obj)).hexdigest()
    return hashlib.sha1(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def strip_private(values):
    return {k: v for k, v in (values or {}).items() if k not in PRIVATE_KEYS}


def _three_way(local, remote, snap):
    """Решить по каждой записи, что делать. local: {id: (hash, mtime)}, remote: {id: doc}, snap: {id: hash}.
    Возвращает (push, pull, delete_local, tombstone, новый снимок)."""
    push, pull, del_local, tomb, new = [], [], [], [], {}
    for i in set(local) | set(remote) | set(snap):
        L = local.get(i)
        R = remote.get(i)
        S = snap.get(i)
        r_live = R is not None and not R.get("deleted")
        r_dead = R is not None and R.get("deleted")
        if L is not None and r_live:
            if L[0] == R.get("hash"):
                new[i] = L[0]
            elif S == L[0]:
                pull.append(i)
            elif S == R.get("hash"):
                push.append(i)
            elif float(R.get("updated") or 0) > float(L[1] or 0):
                pull.append(i)
            else:
                push.append(i)
        elif L is not None and r_dead:
            if S == L[0]:
                del_local.append(i)                # удалили на другом компьютере
            else:
                push.append(i)                     # здесь запись меняли позже — возвращаем её
        elif L is not None:
            push.append(i)                         # в облаке ещё нет
        elif r_live:
            if S is not None and S == R.get("hash"):
                tomb.append(i)                     # удалили здесь
            else:
                pull.append(i)                     # новое с другого компьютера
        # иначе записи нет нигде — из снимка она просто уходит
    return push, pull, del_local, tomb, new


def sync(uri, local, snap, private_local=False, status=None):
    """Одна синхронизация. local и snap — как их собрала программа (см. ниже); возвращает, что применить локально.

    local = {"stamps":   {id: {"meta": {...}, "data": bytes, "mtime": t}},
             "clients":  {ключ: {"values": {...}, "mtime": t}},
             "settings": {имя: {"value": ..., "mtime": t}},
             "counters": {шаблон: {"last", "mode", "reset", "ts", "forced_ts"}}}
    """
    say = status or (lambda _t: None)
    snap = {k: dict((snap or {}).get(k) or {}) for k in ("stamps", "clients", "settings")}
    out = {"stamps_put": {}, "stamps_del": [], "clients_put": {}, "clients_del": [], "settings_put": {},
           "counters": {}, "snap": {}, "up": 0, "down": 0, "removed": 0}
    now = time.time()
    client = connect(uri)
    try:
        db = database(client)

        # ---- печати и подписи: сначала только описания, сами картинки — по необходимости
        say("Сверяю печати…")
        l_st = {}
        for i, e in (local.get("stamps") or {}).items():
            l_st[i] = (digest([e["meta"], digest(e["data"])]), e.get("mtime", 0))
        r_st = {d["_id"]: d for d in db["stamps"].find({}, {"data": 0})}
        push, pull, del_local, tomb, new = _three_way(l_st, r_st, snap["stamps"])
        for i in push:
            e = local["stamps"][i]
            db["stamps"].update_one({"_id": i}, {"$set": {"meta": e["meta"], "data": bytes(e["data"]), "hash": l_st[i][0],
                                                           "updated": now, "deleted": False}}, upsert=True)
            new[i] = l_st[i][0]
        for i in pull:
            d = db["stamps"].find_one({"_id": i})
            if d and d.get("data") is not None:
                out["stamps_put"][i] = {"meta": d.get("meta") or {}, "data": bytes(d["data"]),
                                        "was": l_st[i][0] if i in l_st else None}
                new[i] = d.get("hash")
        for i in tomb:
            db["stamps"].update_one({"_id": i}, {"$set": {"deleted": True, "updated": now}, "$unset": {"data": ""}})
        out["stamps_del"] = [(i, l_st[i][0]) for i in del_local]
        out["snap"]["stamps"] = new
        out["up"] += len(push) + len(tomb)
        out["down"] += len(out["stamps_put"])
        out["removed"] += len(del_local)

        # ---- карточки клиентов
        say("Сверяю клиентов…")
        l_cl, pay = {}, {}
        for k, e in (local.get("clients") or {}).items():
            pay[k] = strip_private(e["values"]) if private_local else dict(e["values"])
            l_cl[k] = (digest(pay[k]), e.get("mtime", 0))
        r_cl = {d["_id"]: d for d in db["clients"].find({})}
        push, pull, del_local, tomb, new = _three_way(l_cl, r_cl, snap["clients"])
        for k in push:
            if not pay[k]:
                continue
            db["clients"].update_one({"_id": k}, {"$set": {"values": pay[k], "hash": l_cl[k][0], "updated": now,
                                                            "deleted": False}}, upsert=True)
            new[k] = l_cl[k][0]
        for k in pull:
            out["clients_put"][k] = {"values": dict(r_cl[k].get("values") or {}), "was": l_cl[k][0] if k in l_cl else None}
            new[k] = r_cl[k].get("hash")
        for k in tomb:
            db["clients"].update_one({"_id": k}, {"$set": {"deleted": True, "updated": now, "values": {}}})
        out["clients_del"] = [(k, l_cl[k][0]) for k in del_local]
        out["snap"]["clients"] = new
        out["up"] += len(push) + len(tomb)
        out["down"] += len(pull)

        # ---- настройки: свои поля шаблонов, наборы ручки, шаблоны имён
        say("Сверяю настройки…")
        l_se = {n: (digest(e["value"]), e.get("mtime", 0)) for n, e in (local.get("settings") or {}).items()}
        r_se = {d["_id"]: d for d in db["settings"].find({})}
        push, pull, _dl, _tb, new = _three_way(l_se, r_se, snap["settings"])
        for n in push:
            db["settings"].update_one({"_id": n}, {"$set": {"value": local["settings"][n]["value"], "hash": l_se[n][0],
                                                             "updated": now, "deleted": False}}, upsert=True)
            new[n] = l_se[n][0]
        for n in pull:
            out["settings_put"][n] = {"value": r_se[n].get("value"), "was": l_se[n][0] if n in l_se else None}
            new[n] = r_se[n].get("hash")
        out["snap"]["settings"] = new
        out["up"] += len(push)
        out["down"] += len(pull)

        # ---- счётчики номеров: побеждает больший номер, а ручная правка — если она новее
        from stamp_word import number_value
        l_ct = local.get("counters") or {}
        r_ct = {d["_id"]: d for d in db["counters"].find({})}
        for t in set(l_ct) | set(r_ct):
            a, b = dict(l_ct.get(t) or {}), dict(r_ct.get(t) or {})
            b.pop("_id", None)
            if not b:
                merged = a
            elif not a:
                merged = b
            else:
                newer = a if float(a.get("ts") or 0) >= float(b.get("ts") or 0) else b
                merged = dict(newer)
                fa, fb = float(a.get("forced_ts") or 0), float(b.get("forced_ts") or 0)
                if fa > float(b.get("ts") or 0) and fa >= fb:
                    merged["last"] = a.get("last", "")
                elif fb > float(a.get("ts") or 0) and fb > fa:
                    merged["last"] = b.get("last", "")
                else:
                    merged["last"] = max((a.get("last", ""), b.get("last", "")), key=number_value)
                merged["ts"] = max(float(a.get("ts") or 0), float(b.get("ts") or 0))
                merged["forced_ts"] = max(fa, fb)
            if merged != b:
                db["counters"].update_one({"_id": t}, {"$set": merged}, upsert=True)
            if merged != a:
                out["counters"][t] = merged
    finally:
        try:
            client.close()
        except Exception:
            pass
    return out


def claim_number(uri, tpl, wanted, auto=True, year=None, reset=True, timeout_ms=3500):
    """Занять номер документа в облаке, чтобы у двух менеджеров не вышло одинаковых.
    Возвращает номер, который нужно поставить (совпадает с wanted, если он свободен)."""
    from stamp_word import next_number, number_value
    client = connect(uri, timeout_ms)
    try:
        col = database(client)["counters"]
        for _ in range(6):
            doc = col.find_one({"_id": tpl}) or {}
            last = str(doc.get("last") or "")
            new_year = bool(year and str(year) in str(wanted) and last and str(year) not in last)
            if not last or new_year or number_value(wanted) > number_value(last) or not auto:
                new = wanted
            else:
                new = next_number(last, year, reset)        # номер уже занят — берём следующий свободный
            keep = new if (not last or new_year or number_value(new) >= number_value(last)) else last
            flt = {"_id": tpl, "last": last} if doc else {"_id": tpl}
            try:
                res = col.update_one(flt, {"$set": {"last": keep, "ts": time.time()}}, upsert=not doc)
            except Exception as e:
                if "duplicate" in str(e).lower():
                    continue
                raise
            if res.matched_count or res.upserted_id is not None:
                return new
        return wanted
    finally:
        try:
            client.close()
        except Exception:
            pass


def selftest():
    """Проверка в собранной программе: драйвер базы и шифрование строки на месте."""
    try:
        import pymongo
        import dns.resolver                                    # нужен для mongodb+srv://
        s = "mongodb+srv://user:secret@cluster0.example.mongodb.net/"
        ok = unprotect(protect(s)) == s and "secret" not in mask(s)
        pymongo.MongoClient("mongodb://127.0.0.1:1/", connect=False, serverSelectionTimeoutMS=200).close()
        if sys.platform == "win32" and not is_encrypted(protect(s)):
            return "bad:dpapi"
        return "ok" if ok else "bad"
    except Exception as e:
        return "fail:" + str(e)[:80]
