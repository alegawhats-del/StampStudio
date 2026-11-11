# -*- coding: utf-8 -*-
"""
ИИ-помощник Stamp Studio: провайдеры (OpenAI-совместимые API), ключи, запросы,
чтение документа, поиск мест для печати и подписи, распознавание текста.
Здесь нет интерфейса — только логика; окна живут в stamp_studio*.py.
"""

import base64
import datetime
import io
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from PIL import Image

# эти три функции подставляет основная программа
SETTINGS_LOAD = lambda: {}
SETTINGS_SAVE = lambda d: None
FIND_RESOURCE = lambda name: None

MM = 72.0 / 25.4

# --------------------------------------------------------------------------- провайдеры
# Имена совпадают с именами в секрете FREE_KEYS (тот же шаблон, что и в Whispy).
PROVIDERS = [
    {"name": "Google Gemini",
     "short": "сканы, рукопись, всё подряд",
     "why": "самое сильное зрение: читает плохие сканы, печати поверх текста и почерк; понимает русский, украинский, польский, немецкий",
     "tasks": "имя файла, данные из документа, проверка, место печати на скане",
     "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "models": ["gemini-flash-latest", "gemini-3.8-flash", "gemini-2.5-flash"],
     "pick": r"gemini-.*flash(?!.*(image|tts|live|audio|lite))",
     "key_url": "https://aistudio.google.com/apikey", "key_hint": "AIza…",
     "limit": 250, "stars": 5,
     "best": "лучше всех читает сканы и рукописный текст — имя файла, данные, проверка"},
    {"name": "NVIDIA NIM (бесплатно)",
     "short": "запасной для сканов",
     "why": "нет дневного лимита — выручает, когда у Gemini кончились запросы; отвечает медленнее",
     "tasks": "данные и проверка больших документов, сканы",
     "url": "https://integrate.api.nvidia.com/v1/chat/completions",
     "models": ["nvidia/nemotron-3.5-super-vl-120b-a12b", "moonshotai/kimi-k2.5",
                "meta/llama-3.2-90b-vision-instruct"],
     "pick": r"(-vl-|vision|omni|kimi-k2\.5|llama-4)",
     "key_url": "https://build.nvidia.com/settings/api-keys", "key_hint": "nvapi-…",
     "limit": 0, "stars": 4,
     "best": "запасной для сканов: без дневного лимита, до 40 запросов в минуту"},
    {"name": "Z.AI GLM (бесплатно)",
     "short": "сканы и таблицы",
     "why": "хорошо разбирает таблицы и бланки (CMR, счета), лимита на день нет; в именах и фамилиях ошибается чаще Gemini",
     "tasks": "данные из бланков и таблиц, имя файла",
     "url": "https://api.z.ai/api/paas/v4/chat/completions",
     "models": ["glm-4.6v-flash", "glm-5.3-flash", "glm-4.6v"],
     "pick": r"glm-.*(v-flash|v$|flash)",
     "key_url": "https://z.ai/manage-apikey/apikey-list", "key_hint": "длинная строка",
     "limit": 0, "stars": 4,
     "best": "сканы и таблицы, без дневного лимита"},
    {"name": "Groq (быстро, бесплатно)",
     "short": "самый быстрый",
     "why": "ответ за 1–3 секунды; мелкий и плохо пропечатанный текст читает хуже",
     "tasks": "имя файла и данные из чётких документов",
     "url": "https://api.groq.com/openai/v1/chat/completions",
     "models": ["qwen/qwen3.8-27b", "meta-llama/llama-4-scout-17b-16e-instruct"],
     "pick": r"(qwen3|llama-4|vision)",
     "key_url": "https://console.groq.com/keys", "key_hint": "gsk_…",
     "limit": 1000, "stars": 3,
     "best": "самый быстрый ответ: имя файла и данные из чётких документов"},
    {"name": "Ollama Cloud (бесплатно)",
     "short": "документы с текстом",
     "why": "сильные текстовые модели, но картинку понимает не каждая — сканы уходят текстом, распознанным на компьютере",
     "tasks": "проверка документов, в которых есть текст",
     "url": "https://ollama.com/v1/chat/completions",
     "models": ["gemma4:31b", "kimi-k3", "glm-5.3-flash", "gpt-oss:120b"],
     "pick": r"(gemma|kimi|glm|vl|vision)",
     "key_url": "https://ollama.com/settings/keys", "key_hint": "длинная строка",
     "limit": 0, "stars": 3,
     "best": "проверка документов с текстом; сканы картинкой понимает не каждая модель"},
    {"name": "Mistral (бесплатно)",
     "short": "европейский, видит сканы",
     "why": "бесплатный тариф без карты, модели понимают картинки; хорошо знает европейские языки — польский, немецкий, французский",
     "tasks": "данные и имя файла для европейских документов (CMR, инвойсы)",
     "url": "https://api.mistral.ai/v1/chat/completions",
     "models": ["mistral-small-latest", "pixtral-large-latest", "mistral-medium-latest"],
     "pick": r"(mistral-(small|medium)|pixtral).*latest",
     "key_url": "https://console.mistral.ai/api-keys", "key_hint": "строка из 32 знаков",
     "limit": 0, "stars": 4,
     "best": "сканы и европейские языки, бесплатный тариф"},
    {"name": "OpenRouter (бесплатные модели)",
     "short": "много моделей одним ключом",
     "why": "один ключ открывает десятки моделей, часть бесплатные; на бесплатных всего около 50 запросов в день",
     "tasks": "запасной вариант, когда остальные недоступны",
     "url": "https://openrouter.ai/api/v1/chat/completions",
     "models": ["openrouter/free"],
     "pick": r"(gemini|gemma|qwen|llama-4|mistral).*:free",
     "key_url": "https://openrouter.ai/keys", "key_hint": "sk-or-…",
     "limit": 50, "stars": 3,
     "best": "десятки моделей одним ключом, часть бесплатные"},
    {"name": "GitHub Models (бесплатно)",
     "short": "ключ — токен GitHub",
     "why": "бесплатный доступ к моделям OpenAI и другим по токену GitHub; лимит небольшой — десятки запросов в день",
     "tasks": "проверка и данные, когда нужен ответ уровня GPT без оплаты",
     "url": "https://models.github.ai/inference/chat/completions",
     "models": ["openai/gpt-4.1-mini", "openai/gpt-4o-mini"],
     "pick": r"openai/gpt-.*mini",
     "key_url": "https://github.com/settings/personal-access-tokens", "key_hint": "github_pat_… (право Models: read)",
     "limit": 50, "stars": 4,
     "best": "модели OpenAI бесплатно по токену GitHub"},
    {"name": "Cerebras (бесплатно)",
     "short": "очень быстрый, только текст",
     "why": "отвечает мгновенно, но картинки не понимает — сканы уходят текстом, распознанным на компьютере; при регистрации может попросить карту",
     "tasks": "проверка и данные из документов с текстом",
     "url": "https://api.cerebras.ai/v1/chat/completions",
     "models": ["gpt-oss-120b", "llama-3.3-70b"],
     "pick": r"(gpt-oss|llama|qwen)",
     "key_url": "https://cloud.cerebras.ai", "key_hint": "csk-…",
     "limit": 0, "stars": 3,
     "best": "мгновенный ответ для документов с текстом"},
    {"name": "OpenAI (платно)", "paid": True,
     "short": "GPT, платный",
     "why": "стабильное высокое качество на сканах и в проверке; оплата за каждый запрос, нужен счёт с балансом",
     "tasks": "всё, когда важна точность и не жалко копеек за запрос",
     "url": "https://api.openai.com/v1/chat/completions",
     "models": ["gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini"],
     "pick": r"^gpt-[0-9.]+o?-mini$",
     "key_url": "https://platform.openai.com/api-keys", "key_hint": "sk-…",
     "limit": 0, "stars": 5,
     "best": "высокая точность, оплата за запрос"},
    {"name": "Anthropic Claude (платно)", "paid": True,
     "short": "Claude, платный",
     "why": "лучше всех находит несостыковки и ошибки в длинных договорах, аккуратен с цифрами; оплата за запрос",
     "tasks": "проверка перед отправкой, данные из сложных документов",
     "url": "https://api.anthropic.com/v1/chat/completions",
     "models": ["claude-haiku-5-5", "claude-sonnet-5-5"],
     "pick": r"claude-(haiku|sonnet)",
     "key_url": "https://console.anthropic.com/settings/keys", "key_hint": "sk-ant-…",
     "limit": 0, "stars": 5,
     "best": "самая внимательная проверка договоров, оплата за запрос"},
    {"name": "xAI Grok (платно)", "paid": True,
     "short": "Grok, платный",
     "why": "быстрые модели со зрением, недорогие; оплата за запрос",
     "tasks": "данные и имя файла со сканов",
     "url": "https://api.x.ai/v1/chat/completions",
     "models": ["grok-4-fast", "grok-4"],
     "pick": r"grok-.*(fast|vision)",
     "key_url": "https://console.x.ai", "key_hint": "xai-…",
     "limit": 0, "stars": 4,
     "best": "быстро и недорого, видит сканы"},
    {"name": "DeepSeek (платно)", "paid": True,
     "short": "дешёвый, только текст",
     "why": "очень дёшево и умно, но картинки не понимает — сканы уходят текстом, распознанным на компьютере",
     "tasks": "проверка и данные из документов с текстом",
     "url": "https://api.deepseek.com/chat/completions",
     "models": ["deepseek-chat"],
     "pick": r"deepseek-chat",
     "key_url": "https://platform.deepseek.com/api_keys", "key_hint": "sk-…",
     "limit": 0, "stars": 3,
     "best": "копеечная проверка документов с текстом"},
    {"name": "Pollinations (без ключа)",
     "short": "работает без ключа",
     "why": "ничего не надо настраивать, но медленнее и слабее остальных, бывают отказы",
     "tasks": "попробовать ИИ до того, как появятся ключи",
     "url": "https://text.pollinations.ai/openai",
     "models": ["openai"], "pick": r"openai", "nokey": True,
     "key_url": "https://pollinations.ai", "key_hint": "ключ не нужен",
     "limit": 0, "stars": 2,
     "best": "работает сразу без ключа, но медленнее и слабее остальных"},
    {"name": "Свой сервис (OpenAI-совместимый)",
     "short": "любой другой сервис",
     "why": "если есть платный ключ OpenAI, OpenRouter или свой сервер — качество зависит от выбранной модели",
     "tasks": "любые",
     "url": "", "models": [], "pick": r".", "custom": True,
     "key_url": "", "key_hint": "ключ вашего сервиса",
     "limit": 0, "stars": 0,
     "best": "любой сервис с адресом вида …/v1/chat/completions (OpenAI, OpenRouter и т. п.)"},
]

DEFAULT_FIELDS = "Тип документа, Номер, Дата, Сумма, Валюта, VIN, Марка и модель, Гос. номер, ФИО, Организация, ИНН/УНП"
DEFAULT_NAME_RULE = "Тип документа №номер Фамилия или организация дата (ДД.ММ.ГГГГ)"


class AiError(Exception):
    pass


class AiCancelled(Exception):
    pass


def provider(name):
    for p in PROVIDERS:
        if p["name"] == name:
            return p
    return None


def _match_provider(name):
    """Имя из FREE_KEYS → провайдер (допускаем неточное написание)."""
    low = (name or "").lower()
    for p in PROVIDERS:
        if p["name"].lower() == low:
            return p["name"]
    for key, target in (("gemini", "Google Gemini"), ("nvidia", "NVIDIA NIM (бесплатно)"),
                        ("groq", "Groq (быстро, бесплатно)"), ("ollama", "Ollama Cloud (бесплатно)"),
                        ("z.ai", "Z.AI GLM (бесплатно)"), ("glm", "Z.AI GLM (бесплатно)"),
                        ("zai", "Z.AI GLM (бесплатно)")):
        if key in low:
            return target
    return None


# --------------------------------------------------------------------------- ключи
_XOR = b"StampStudio-free-keys-v1"


def pack_keys(json_text: str) -> bytes:
    """Секрет FREE_KEYS → файл keys.bin (не шифрование, а защита от случайного чтения)."""
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("FREE_KEYS must be a JSON object")
    clean = {}
    for k, v in data.items():
        name = _match_provider(str(k))
        if name and str(v).strip():
            clean[name] = str(v).strip()
    raw = json.dumps(clean, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(bytes(b ^ _XOR[i % len(_XOR)] for i, b in enumerate(raw)))


_builtin = None


def builtin_keys() -> dict:
    global _builtin
    if _builtin is None:
        _builtin = {}
        try:
            path = FIND_RESOURCE("keys.bin")
            if path:
                with open(path, "rb") as f:
                    raw = base64.b64decode(f.read())
                raw = bytes(b ^ _XOR[i % len(_XOR)] for i, b in enumerate(raw))
                _builtin = json.loads(raw.decode("utf-8"))
        except Exception:
            _builtin = {}
    return _builtin


def key_for(name, s=None):
    """(ключ, откуда): свой ключ важнее встроенного."""
    s = SETTINGS_LOAD() if s is None else s
    k = (s.get("ai_keys") or {}).get(name, "").strip()
    if k:
        return k, "свой"
    k = builtin_keys().get(name, "")
    if k:
        return k, "встроенный"
    return "", ""


def provider_ready(p, s=None):
    if p.get("custom"):
        s = SETTINGS_LOAD() if s is None else s
        return bool((s.get("ai_custom_url") or "").strip())
    return bool(p.get("nokey")) or bool(key_for(p["name"], s)[0])


def count_today(name, s=None):
    s = SETTINGS_LOAD() if s is None else s
    c = (s.get("ai_counts") or {}).get(name, {})
    return c.get("today", 0) if c.get("day") == datetime.date.today().isoformat() else 0


def limit_state(name, s=None):
    """(сегодня, лимит, доля 0..1) — для счётчика и чтобы не упереться в лимит."""
    p = provider(name) or {}
    today = count_today(name, s)
    lim = int(p.get("limit") or 0)
    return today, lim, (today / lim if lim else 0.0)


def provider_order(s=None):
    """Выбранный сервис первым, за ним остальные готовые — для автоперехода.
    Сервисы, у которых дневной лимит по нашему счётчику уже выбран, уходят в конец очереди.
    Если автопереход выключен (ai_failover = False) — только выбранный."""
    s = SETTINGS_LOAD() if s is None else s
    chosen = s.get("ai_provider") or default_provider(s)
    names = [chosen]
    if s.get("ai_failover", True):
        names += [p["name"] for p in PROVIDERS if p["name"] != chosen and not p.get("custom")]
    ready = [provider(n) for n in names if provider(n) and provider_ready(provider(n), s)]
    fresh = [p for p in ready if limit_state(p["name"], s)[2] < 1.0]
    spent = [p for p in ready if limit_state(p["name"], s)[2] >= 1.0]
    return fresh + spent


def default_provider(s=None):
    s = SETTINGS_LOAD() if s is None else s
    for p in PROVIDERS:
        if not p.get("nokey") and not p.get("custom") and key_for(p["name"], s)[0]:
            return p["name"]
    return "Pollinations (без ключа)"


# --------------------------------------------------------------------------- счётчик
def count_inc(name):
    s = SETTINGS_LOAD()
    c = s.setdefault("ai_counts", {}).setdefault(name, {"day": "", "today": 0, "total": 0})
    today = datetime.date.today().isoformat()
    if c.get("day") != today:
        c["day"], c["today"] = today, 0
    c["today"] += 1
    c["total"] = c.get("total", 0) + 1
    SETTINGS_SAVE(s)


def count_text(name, s=None):
    s = SETTINGS_LOAD() if s is None else s
    c = (s.get("ai_counts") or {}).get(name, {})
    today = c.get("today", 0) if c.get("day") == datetime.date.today().isoformat() else 0
    p = provider(name) or {}
    lim = f" из ~{p['limit']}" if p.get("limit") else ""
    return f"Запросов сегодня: {today}{lim} · всего: {c.get('total', 0)}"


# --------------------------------------------------------------------------- HTTP
def _http_json(url, payload=None, key="", timeout=90):
    headers = {"Content-Type": "application/json", "User-Agent": "StampStudio-AI"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return e.code, body
    except Exception as e:                       # нет сети, таймаут, не JSON
        return 0, str(e)


def _err_text(body):
    try:
        d = json.loads(body) if isinstance(body, str) else body
        if isinstance(d, list) and d:
            d = d[0]
        e = d.get("error", d) if isinstance(d, dict) else d
        if isinstance(e, dict):
            return str(e.get("message") or e)[:300]
        return str(e)[:300]
    except Exception:
        return str(body)[:300]


def list_models(p, key, s=None):
    s = SETTINGS_LOAD() if s is None else s
    url = (s.get("ai_custom_url") if p.get("custom") else p["url"]) or ""
    base = url.rsplit("/chat/completions", 1)[0]
    code, data = _http_json(base + "/models", None, key, timeout=20)
    if code != 200 or not isinstance(data, dict):
        return []
    out = []
    for m in data.get("data") or data.get("models") or []:
        mid = m.get("id") or m.get("name") if isinstance(m, dict) else str(m)
        if mid:
            out.append(str(mid).replace("models/", ""))
    return out


def _candidates(p, s):
    user = ((s.get("ai_models") or {}).get(p["name"]) or "").strip()
    found = ((s.get("ai_models_found") or {}).get(p["name"]) or "").strip()
    out = []
    for m in [user, found] + list(p.get("models") or []):
        if m and m not in out:
            out.append(m)
    return out


def _remember_model(name, model):
    s = SETTINGS_LOAD()
    if (s.get("ai_models_found") or {}).get(name) != model:
        s.setdefault("ai_models_found", {})[name] = model
        SETTINGS_SAVE(s)


def _content(text, images):
    if not images:
        return text
    parts = [{"type": "text", "text": text}]
    for im in images:
        parts.append({"type": "image_url", "image_url": {
            "url": "data:image/jpeg;base64," + base64.b64encode(im).decode("ascii")}})
    return parts


def _answer(data):
    try:
        msg = data["choices"][0]["message"]
        c = msg.get("content")
        if isinstance(c, list):
            c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
        return (c or "").strip()
    except Exception:
        return ""


LAST = {"provider": "", "model": "", "mode": "", "problems": []}   # как был получен последний ответ


def _ask_provider(p, s, system, text, images, max_tokens, status, cancel):
    """Один сервис: перебрать его модели. Возвращает (ответ, модель) или бросает AiError с причиной."""
    name = p["name"]
    key = "" if p.get("nokey") else key_for(name, s)[0]
    url = (s.get("ai_custom_url") or "").strip() if p.get("custom") else p["url"]
    models = _candidates(p, s)
    if p.get("custom") and not models:
        models = list_models(p, key, s)[:1]
    tried_discovery = False
    i, last = 0, "нет подходящей модели"
    while i < len(models):
        if cancel and cancel():
            raise AiCancelled()
        model = models[i]
        if status:
            status(f"{name.split(' (')[0]} · {model}" + (" · читает изображения" if images else ""))
        payload = {"model": model, "temperature": 0.1, "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": _content(text, images)}]}
        code, data = _http_json(url, payload, key)
        if cancel and cancel():
            raise AiCancelled()
        if code == 200:
            ans = _answer(data)
            if ans:
                count_inc(name)
                _remember_model(name, model)
                return ans, model
            last = "пустой ответ"
        elif code in (401, 403):
            raise AiError(f"ключ не принят ({code})")
        elif code == 429:
            raise AiError("лимит запросов исчерпан")
        elif code >= 500 or code == 0:
            raise AiError("нет связи с сервисом" if code == 0 else f"сервис недоступен ({code})")
        else:                           # 400/404/413/422: нет такой модели, не видит картинки, слишком большой запрос
            last = f"{code}: " + (_err_text(data) or "запрос не принят")
        i += 1
        if i >= len(models) and not tried_discovery and not p.get("nokey"):
            tried_discovery = True
            try:
                rx = re.compile(p.get("pick") or ".", re.I)
                models += [m for m in list_models(p, key, s) if rx.search(m) and m not in models][:3]
            except Exception:
                pass
    raise AiError(last)


def chat(system, text, images=None, max_tokens=2000, status=None, cancel=None, only=None,
         text_fallback=None, fallback_text=None):
    """Запрос к ИИ с автопереключением. Возвращает (ответ, провайдер, модель).

    Сначала все сервисы по очереди пробуют прочитать ИЗОБРАЖЕНИЯ страниц. Только если ни один
    не смог, уходит текст, распознанный на компьютере (text_fallback) — он с ошибками, поэтому
    для этого случая можно дать другой вопрос (fallback_text)."""
    s = SETTINGS_LOAD()
    order = [provider(only)] if only else provider_order(s)
    order = [p for p in order if p]
    if not order:
        raise AiError("ИИ не настроен: добавьте ключ в меню «ИИ → Настройки ИИ и ключи».")
    problems = []
    LAST.update(provider="", model="", mode="", problems=problems)
    passes = [("изображения страниц" if images else "текст документа", text, images)]
    if images and text_fallback:
        passes.append(("текст, распознанный на компьютере", None, None))
    for mode, body, imgs in passes:
        if body is None:                # второй заход: распознаём на компьютере только теперь
            if status:
                status("Сервисы не прочитали изображения — распознаю текст на компьютере")
            ocr = text_fallback() if callable(text_fallback) else text_fallback
            if not ocr:
                break
            body = (fallback_text or text) + ("\n\nТЕКСТ СТРАНИЦ (распознан автоматически, "
                                              "буквы могут быть искажены):\n" + ocr)
        for p in order:
            try:
                ans, model = _ask_provider(p, s, system, body, imgs, max_tokens, status, cancel)
            except AiError as e:
                problems.append(f"{p['name'].split(' (')[0]}" + (" (картинки)" if imgs else "") + f": {e}")
                continue
            LAST.update(provider=p["name"], model=model, mode=mode)
            return ans, p["name"], model
    raise AiError("Не получилось получить ответ ИИ.\n" + "\n".join("• " + x for x in problems[-8:]))


def test_provider(name):
    """Проверка ключа кнопкой «Проверить»: текст и маленькая картинка."""
    im = Image.new("RGB", (320, 120), "white")
    try:
        from PIL import ImageDraw, ImageFont
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.load_default(size=64)
        except TypeError:
            font = ImageFont.load_default()
        d.text((60, 20), "7 4 1", fill="black", font=font)
    except Exception:
        pass
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    ans, _, model = chat("Отвечай одним словом.", "Ответь словом: работает", None, 20, only=name)
    vision = "не проверено"
    try:
        a2, _, m2 = chat("Отвечай только цифрами.", "Какие цифры на картинке?", [buf.getvalue()], 20, only=name)
        digits = re.sub(r"\D", "", a2)
        vision = f"да ({m2})" if "741" in digits else "отвечает, но цифры прочитал неверно"
    except AiError:
        vision = "нет — сканы будут читаться текстом, распознанным на компьютере"
    return f"Работает · модель {model}\nКартинки (сканы): {vision}"


def extract_json(text):
    """Достать JSON из ответа модели (с ```json, пояснениями до и после)."""
    t = (text or "").strip()
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        a, b = t.find(opener), t.rfind(closer)
        if a != -1 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except Exception:
                try:
                    return json.loads(re.sub(r",\s*([}\]])", r"\1", t[a:b + 1]))
                except Exception:
                    continue
    raise AiError("ИИ ответил не в том виде, который ожидался. Попробуйте ещё раз "
                  "или выберите другого провайдера.\n\n" + (text or "")[:300])


# --------------------------------------------------------------------------- чтение документа
def page_has_text(page):
    """Есть ли у страницы текст: обычный (не пара случайных букв) или распознанный слой."""
    n = len(page.get_text().strip())
    if n >= 40:
        return True
    if n == 0:
        return False
    try:
        return any(sp.get("type") == 3 for sp in page.get_texttrace())
    except Exception:
        return False


def is_scan_page(page):
    """Скан: текста нет вовсе или он только невидимый (распознанный слой — в нём бывают ошибки).
    Такие страницы ИИ должен читать изображением, а не этим текстом."""
    if not page_has_text(page):
        return True
    try:
        spans = [sp for sp in page.get_texttrace() if sp.get("chars")]
        return bool(spans) and all(sp.get("type") == 3 for sp in spans)
    except Exception:
        return False


def page_image(page, long_side=1500):
    r = page.rect
    zoom = long_side / max(r.width, r.height)
    zoom = max(0.5, min(zoom, 4.0))
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def jpeg_bytes(im, quality=72):
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def collect(doc, pages=None, max_images=6, max_chars=14000):
    """Подготовить документ к отправке (вызывать в главном потоке).
    Страницы с текстом идут текстом, сканы — картинками (не больше max_images)."""
    pages = list(range(doc.page_count)) if pages is None else list(pages)
    chunks, images, image_pages, skipped = [], [], [], 0
    used = 0
    for i in pages:
        page = doc[i]
        if not is_scan_page(page):
            t = page.get_text().strip()
            t = re.sub(r"[ \t]+", " ", t)
            t = re.sub(r"\n{3,}", "\n\n", t)
            room = max_chars - used
            if room <= 200:
                skipped += 1
                continue
            t = t[:room]
            used += len(t)
            chunks.append(f"=== Страница {i + 1} ===\n{t}")
        elif len(images) < max_images:
            images.append(jpeg_bytes(page_image(page)))
            image_pages.append(i)
            chunks.append(f"=== Страница {i + 1} === (скан, см. изображение {len(images)})")
        else:
            skipped += 1
    return {"text": "\n\n".join(chunks), "images": images, "image_pages": image_pages,
            "skipped": skipped, "pages": pages}


def ocr_text_for(bundle):
    """Текст сканов, распознанный на компьютере — на случай модели без зрения."""
    if not bundle.get("images") or not win_ocr_available():
        return None
    out = []
    for n, raw in zip(bundle["image_pages"], bundle["images"]):
        try:
            words = win_ocr_words(Image.open(io.BytesIO(raw)))
            out.append(f"=== Страница {n + 1} ===\n" + words_to_text(words))
        except Exception:
            pass
    return "\n\n".join(out) or None


# --------------------------------------------------------------------------- задачи
DATE_ZONES = (
    ("-10", "Гонолулу"), ("-8", "Лос-Анджелес, Ванкувер"), ("-7", "Денвер"), ("-6", "Чикаго, Мехико"),
    ("-5", "Нью-Йорк, Торонто"), ("-3", "Буэнос-Айрес, Сан-Паулу"), ("0", "Лондон, Лиссабон (зима)"),
    ("1", "Берлин, Варшава, Париж (зима) · Лондон (лето)"), ("2", "Калининград, Киев, Вильнюс (зима) · Берлин, Варшава (лето)"),
    ("3", "Москва, Минск, Стамбул · Киев, Вильнюс (лето)"), ("3.5", "Тегеран"), ("4", "Самара, Тбилиси, Баку, Дубай"),
    ("4.5", "Кабул"), ("5", "Екатеринбург, Ташкент, Астана"), ("5.5", "Дели"), ("6", "Омск, Бишкек"),
    ("7", "Новосибирск, Красноярск, Бангкок"), ("8", "Иркутск, Пекин, Сингапур"), ("9", "Якутск, Токио, Сеул"),
    ("9.5", "Аделаида"), ("10", "Владивосток, Сидней"), ("11", "Магадан, Сахалин"), ("12", "Камчатка, Окленд"))


def zone_title(key):
    try:
        h = float(key)
    except (TypeError, ValueError):
        return "как на этом компьютере"
    sign = "+" if h >= 0 else "−"
    hh, mm = int(abs(h)), int(round((abs(h) % 1) * 60))
    return f"UTC{sign}{hh:02d}:{mm:02d}  {dict(DATE_ZONES).get(str(key), '')}".strip()


def date_settings(s=None):
    """(режим, пояс, сдвиг дней): режим «pc» — часы компьютера, «zone» — часовой пояс, «manual» — своя дата."""
    try:
        s = (SETTINGS_LOAD() or {}) if s is None else s
    except Exception:
        s = {}
    zone = str(s.get("date_zone") or "pc")
    mode = s.get("date_mode") or ("pc" if zone == "pc" else "zone")
    try:
        shift = int(s.get("date_shift") or 0)
    except (TypeError, ValueError):
        shift = 0
    return mode, zone, shift


def now(s=None):
    """Текущие дата и время так, как их считает программа (и ИИ)."""
    mode, zone, shift = date_settings(s)
    if mode == "zone" and zone != "pc":
        try:
            tz = datetime.timezone(datetime.timedelta(hours=float(zone)))
            return datetime.datetime.now(tz).replace(tzinfo=None)
        except Exception:
            pass
    t = datetime.datetime.now()
    if mode == "manual" and shift:
        t += datetime.timedelta(days=shift)
    return t


def today():
    return now().date()


def today_text(with_time=False):
    t = now()
    out = f"{t.strftime('%d.%m.%Y')}, {('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')[t.weekday()]}"
    return out + t.strftime(" %H:%M") if with_time else out


def internet_time(timeout=8):
    """Точное время из интернета (UTC) — по заголовку ответа сервера. None, если сети нет."""
    from email.utils import parsedate_to_datetime
    for url in ("https://www.google.com/generate_204", "https://github.com", "https://www.cloudflare.com"):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "StampStudio"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = r.headers.get("Date")
            if d:
                return parsedate_to_datetime(d).astimezone(datetime.timezone.utc).replace(tzinfo=None)
        except Exception:
            continue
    return None


OFFICE_EXT = (".docx", ".doc", ".rtf", ".odt")


def _word_com_pdf(path):
    """PDF из документа через установленный Microsoft Word — вид точно как при печати."""
    import tempfile
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    tmp = tempfile.mkdtemp(prefix="stampstudio_w_")
    out = os.path.join(tmp, "doc.pdf")
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        d = word.Documents.Open(os.path.abspath(path), ConfirmConversions=False, ReadOnly=True,
                                AddToRecentFiles=False)
        try:
            d.ExportAsFixedFormat(out, 17)             # 17 = PDF
        finally:
            d.Close(False)
        with open(out, "rb") as f:
            return f.read()
    finally:
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        try:
            if os.path.exists(out):
                os.remove(out)
            os.rmdir(tmp)
        except OSError:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def office_to_pdf(path):
    """Документ Word → PDF в памяти. Возвращает (bytes, "word" | "simple"). Исходный файл не меняется."""
    err = ""
    if sys.platform == "win32":
        try:
            data = _word_com_pdf(path)
            if data and data[:4] == b"%PDF":
                return data, "word"
        except Exception as e:
            err = str(e)
    if not path.lower().endswith(".docx"):
        raise RuntimeError("Этот формат открывается только через Microsoft Word, а Word на компьютере "
                           "не найден или не ответил. Сохраните документ как .docx или PDF."
                           + (f"\n({err[:160]})" if err else ""))
    import fitz
    src = fitz.open(path)
    try:
        try:
            src.layout(width=595, height=842, fontsize=11)
        except Exception:
            pass
        data = src.convert_to_pdf()
    finally:
        src.close()
    return data, "simple"


def sys_prompt():
    today_s = today().strftime("%d.%m.%Y")
    return ("Ты помощник по документам (договоры, CMR, счета, акты, доверенности, таможенные и "
            "автомобильные документы; русский, украинский, белорусский, английский, польский, немецкий). "
            f"Сегодня {today_s} — документ с этой или близкой датой составлен "
            "сейчас, это нормально, такая дата не «неправильная» и не «в будущем». "
            "Читай внимательно, ничего не выдумывай: если чего-то в документе нет — оставляй пустую строку. "
            "Отвечай только JSON без пояснений.")


def clean_filename(name, limit=120):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(name or ""))
    name = re.sub(r"\s+", " ", name).strip(" .")
    if name.lower().endswith(".pdf"):
        name = name[:-4].rstrip(" .")
    return name[:limit].rstrip(" .")


def task_name(bundle, rule=None, status=None, cancel=None):
    rule = (rule or SETTINGS_LOAD().get("ai_name_rule") or DEFAULT_NAME_RULE).strip()
    q = ("Придумай короткое имя файла для этого документа.\n"
         f"Правило имени: {rule}\n"
         "Пример: «CMR №597 Иванов 26.09.2026». Без расширения, без кавычек, без символов \\ / : * ? \" < > |. "
         "Если какой-то части в документе нет — пропусти её. Дату бери из самого документа.\n"
         'Ответ: {"name": "...", "type": "...", "number": "...", "date": "ДД.ММ.ГГГГ", "party": "..."}\n\n'
         "ДОКУМЕНТ:\n" + bundle["text"])
    ans, prov, model = chat(sys_prompt(), q, bundle["images"], 400, status, cancel, text_fallback=lambda: ocr_text_for(bundle))
    d = extract_json(ans)
    name = clean_filename(d.get("name") if isinstance(d, dict) else "")
    if not name:
        raise AiError("ИИ не смог придумать имя: в документе не нашлось ни типа, ни номера, ни даты.")
    return {"name": name, "provider": prov, "model": model}


def fields_list(text=None):
    text = text if text is not None else (SETTINGS_LOAD().get("ai_fields") or DEFAULT_FIELDS)
    out = []
    for f in re.split(r"[,;\n]+", text):
        f = f.strip()
        if f and f not in out:
            out.append(f)
    return out or fields_list(DEFAULT_FIELDS)


def task_extract(bundle, fields=None, status=None, cancel=None):
    fields = fields or fields_list()
    q = ("Выпиши из документа данные.\n"
         "Обязательные поля (ровно с такими названиями, в этом порядке): " + "; ".join(fields) + ".\n"
         "Если значений несколько (две стороны, несколько сумм) — перечисли через «; ». "
         "Суммы пиши цифрами как в документе, даты — ДД.ММ.ГГГГ, VIN — 17 знаков без пробелов.\n"
         "В «other» добавь до 8 других важных данных, которых нет в списке (адреса, банк, срок, маршрут).\n"
         'Ответ: {"fields": [{"name": "...", "value": "..."}], "other": [{"name": "...", "value": "..."}]}\n\n'
         "ДОКУМЕНТ:\n" + bundle["text"])
    ans, prov, model = chat(sys_prompt(), q, bundle["images"], 1800, status, cancel, text_fallback=lambda: ocr_text_for(bundle))
    d = extract_json(ans)
    got = {}
    rows = d.get("fields") if isinstance(d, dict) else None
    if isinstance(rows, dict):
        rows = [{"name": k, "value": v} for k, v in rows.items()]
    for r in rows or []:
        if isinstance(r, dict):
            v = r.get("value")
            if isinstance(v, (list, tuple)):
                v = "; ".join(str(x) for x in v)
            got[str(r.get("name", "")).strip().lower()] = "" if v is None else str(v).strip()
    out = [(f, got.get(f.lower(), "")) for f in fields]
    other = []
    for r in (d.get("other") if isinstance(d, dict) else None) or []:
        if isinstance(r, dict) and str(r.get("value") or "").strip():
            other.append((str(r.get("name", "")).strip(), str(r.get("value")).strip()))
    return {"fields": out, "other": other[:8], "provider": prov, "model": model}


_UNITS = {"ноль": 0, "один": 1, "одна": 1, "одно": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
          "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12,
          "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
          "восемнадцать": 18, "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40,
          "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
          "сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500, "шестьсот": 600,
          "семьсот": 700, "восемьсот": 800, "девятьсот": 900}
_SCALES = (("тысяч", 1000), ("миллион", 10 ** 6), ("миллиард", 10 ** 9))


def words_to_number(text):
    """«Один миллион девятьсот девяносто две тысячи» → 1992000. None, если это не число словами."""
    total = cur = 0
    seen = False
    for w in re.findall(r"[а-яё]+", (text or "").lower()):
        if w in _UNITS:
            cur += _UNITS[w]
            seen = True
            continue
        for stem, mult in _SCALES:
            if w.startswith(stem):
                total += (cur or 1) * mult
                cur = 0
                seen = True
                break
    return total + cur if seen else None


def sum_in_words_ok(quote):
    """True — в цитате сумма цифрами и прописью совпадают; False — расходятся; None — проверить нельзя."""
    m = re.search(r"(\d[\d\s\u00a0.]*)(?:[,.](\d{1,2}))?\s*\(([^)]{3,})\)", quote or "")
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    words = words_to_number(m.group(3))
    if not digits or words is None:
        return None
    return int(digits) == words


_VAGUE = re.compile(r"^\s*(не)?(правильн|верн|корректн|точн)\w*\s+[^.:—-]{0,60}$", re.I)


def filter_issues(issues):
    """Убрать замечания, которые ИИ не обосновал или которые опровергаются простой проверкой."""
    out = []
    for it in issues:
        text, quote, why = it["text"], it["quote"], it.get("expected", "")
        low = (text + " " + why).lower()
        if "пропис" in low and sum_in_words_ok(quote) is True:
            continue                                   # сумма прописью пересчитана: она верная
        if _VAGUE.match(text) and not why:
            continue                                   # «Неправильная дата» без объяснения — не замечание
        if why and why.strip(" .«»\"").lower() == quote.strip(" .«»\"").lower():
            continue                                   # «должно быть» то же самое, что и написано
        if re.search(r"\b(ноль|0[,.]00|бесплатн)", quote.lower()) and re.search(r"стоимост|цен|тариф|сумм", low) \
                and not re.search(r"не совпад|расход|противореч|в другом месте|на стр", low):
            continue                                   # ноль / бесплатно — допустимое значение
        out.append(it)
    return out


def task_card(bundle, keys, status=None, cancel=None):
    """Данные клиента и автомобиля из паспорта, техпаспорта, инвойса. keys: [(ключ, название)].
    Возвращает {"values": {ключ: значение}, "provider", "model"}."""
    lines = "\n".join(f'  "{k}": {title}' for k, title in keys)
    q = ("Перед тобой документы клиента: паспорт, свидетельство о регистрации автомобиля (техпаспорт), инвойс "
         "или договор купли-продажи. Выпиши данные в JSON с такими ключами:\n" + lines + "\n"
         "Правила: ФИО — в именительном падеже, кириллицей, как в паспорте. Паспорт — серия и номер через пробел. "
         "Даты — ДД.ММ.ГГГГ. VIN — 17 знаков без пробелов. Объём двигателя — число и «см³». Вес — только число в кг. "
         "Чего в документах нет — оставь пустую строку, ничего не выдумывай и не угадывай.\n"
         'Ответ: {"values": {"fio": "...", "passport": "..."}}\n\n'
         "ДОКУМЕНТЫ:\n" + bundle["text"])
    ans, prov, model = chat(sys_prompt(), q, bundle["images"], 1500, status, cancel,
                            text_fallback=lambda: ocr_text_for(bundle))
    d = extract_json(ans)
    vals = d.get("values") if isinstance(d, dict) and isinstance(d.get("values"), dict) else (d if isinstance(d, dict) else {})
    allowed = {k for k, _t in keys}
    out = {}
    for k, v in (vals or {}).items():
        if k in allowed and v is not None and str(v).strip() and str(v).strip().lower() not in ("нет", "-", "—", "null", "none"):
            out[k] = str(v).strip()
    return {"values": out, "provider": prov, "model": model}


def task_check(bundle, status=None, cancel=None):
    answer = ('Ответ: {"summary": "одна фраза", "issues": [{"page": 1, "severity": "error", '
              '"text": "что именно не так", "quote": "точная цитата из документа", '
              '"expected": "как должно быть ИЛИ с чем не совпадает (цитата второго места и его страница)"}]}\n\n')
    common = ("ЖЁСТКИЕ ПРАВИЛА:\n"
              "• Ты не знаешь, какие ФИО, паспортные данные, адреса, номера, даты и суммы «правильные». "
              "Нельзя писать «неправильное ФИО / дата / сумма» само по себе. Замечание допустимо, только если "
              "ты показываешь ДВА места документа, которые противоречат друг другу, либо явную ошибку в слове.\n"
              "• Поле «expected» обязательно: что должно быть написано или с чем расходится. Не можешь заполнить — "
              "не сообщай об этом.\n"
              "• Сумму прописью проверяй пересчётом: переведи слова в число и сравни с цифрами. Совпало — всё верно.\n"
              "• Ноль, «0,00», «бесплатно», «не предусмотрено» — допустимые значения, не ошибка.\n"
              "• Дата документа, равная сегодняшней или близкая к ней, — нормальная.\n"
              "• Лучше не сообщить ничего, чем сообщить о том, в чём не уверен. Если проблем нет — пустой список.\n"
              "Не придирайся к стилю и оформлению.\n"
              "В «page» ставь номер страницы из заголовка «=== Страница N ===».\n"
              "severity: «error» — нельзя отправлять, «warn» — стоит глянуть.\n")
    q = ("Проверь документ перед отправкой. Ищи только настоящие проблемы:\n"
         "1) опечатки и ошибки в словах, именах, названиях — только те, что действительно напечатаны в документе. "
         "Если слово плохо видно (скан, печать поверх текста, подпись) — это не опечатка, пропусти его;\n"
         "2) несовпадения внутри документа и между страницами: даты, суммы (цифрами и прописью), "
         "номера, VIN, реквизиты, ФИО, названия организаций;\n"
         "3) незаполненные места: пустые поля, «____», пропущенные дата, номер, подпись;\n"
         "4) арифметика: итог не сходится со строками.\n"
         "УНП, ИНН, ОГРН, БИН, ЕГРПОУ — обычные реквизиты разных стран, сами по себе не ошибка.\n"
         + common + answer + "ДОКУМЕНТ:\n" + bundle["text"])
    # если картинки прочитать не удалось и уходит автоматически распознанный текст —
    # искажённые буквы в нём НЕ опечатки документа, поэтому орфографию не проверяем вовсе
    q_ocr = ("Проверь документ перед отправкой. ВАЖНО: текст ниже получен автоматическим распознаванием скана, "
             "в нём искажены буквы («тода» вместо «года», «рохийских» вместо «российских»). "
             "Это ошибки распознавания, а НЕ документа: об опечатках и странных словах не сообщай вообще.\n"
             "Проверяй только по смыслу:\n"
             "1) несовпадения дат, сумм (цифрами и прописью), номеров, VIN, ФИО и реквизитов между частями документа;\n"
             "2) незаполненные места: пустые поля, «____», пропущенные дата, номер;\n"
             "3) арифметику: итог не сходится со строками.\n"
             "Сообщай только о том, в чём уверен, несмотря на искажения. В «quote» восстанови нормальное написание.\n"
             + common + answer + "ДОКУМЕНТ:\n" + bundle["text"])
    ans, prov, model = chat(sys_prompt(), q, bundle["images"], 2500, status, cancel,
                            text_fallback=lambda: ocr_text_for(bundle), fallback_text=q_ocr)
    mode, problems = LAST.get("mode", ""), list(LAST.get("problems") or [])
    d = extract_json(ans)
    issues = []
    for r in (d.get("issues") if isinstance(d, dict) else d if isinstance(d, list) else None) or []:
        if not isinstance(r, dict) or not str(r.get("text") or "").strip():
            continue
        try:
            page = int(r.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        issues.append({"page": page, "severity": "error" if str(r.get("severity")).lower().startswith("err") else "warn",
                       "text": str(r.get("text")).strip(), "quote": str(r.get("quote") or "").strip(),
                       "expected": str(r.get("expected") or "").strip()})
    raw_count = len(issues)
    issues = filter_issues(issues)
    issues.sort(key=lambda x: (x["severity"] != "error", x["page"]))
    return {"summary": str(d.get("summary") or "").strip() if isinstance(d, dict) else "",
            "issues": issues, "skipped": bundle.get("skipped", 0), "provider": prov, "model": model,
            "mode": mode, "problems": problems, "dropped": raw_count - len(issues)}


# --------------------------------------------------------------------------- слова на странице
def page_words(page):
    """Слова из текстового слоя: [(x0, y0, x1, y1, текст)] в пунктах страницы, как она видна."""
    out = []
    for w in page.get_text("words"):
        r = fitz.Rect(w[:4]) * page.rotation_matrix if page.rotation else fitz.Rect(w[:4])
        r.normalize()
        out.append((r.x0, r.y0, r.x1, r.y1, w[4]))
    return out


def words_to_text(words):
    lines, cur, last_y = [], [], None
    for w in sorted(words, key=lambda w: (round((w[1] + w[3]) / 2 / 6), w[0])):
        y = (w[1] + w[3]) / 2
        if last_y is not None and abs(y - last_y) > max(4, (w[3] - w[1]) * 0.6):
            lines.append(" ".join(cur)); cur = []
        cur.append(w[4]); last_y = y
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines)


_LOOK = str.maketrans("mpMPnNhHoOcCeEaAxXkKtTbByY", "мпМПпПнНоОсСеЕаАхХкКтТвВуУ")


def _letters(t):
    return re.sub(r"[^a-zа-яёіїєґў]", "", t.translate(_LOOK).lower())


def find_marks(words):
    """Найти места для печати («М.П.», «место печати») и подписи («подпись», «____»).
    Возвращает (печати, подписи): списки (cx, cy, bbox)."""
    stamps, signs = [], []
    n = len(words)
    for i, w in enumerate(words):
        t = w[4]
        L = _letters(t)
        box = list(w[:4])
        hit = False
        if L == "мп" and ("." in t or t.strip("().,:;").isupper()) and len(t) <= 7:
            hit = True
        elif L == "м" and i + 1 < n and _letters(words[i + 1][4]) == "п" and len(t) <= 3 \
                and abs(words[i + 1][1] - w[1]) < (w[3] - w[1]) and words[i + 1][0] - w[2] < (w[3] - w[1]) * 2.5:
            nb = words[i + 1]
            box = [min(w[0], nb[0]), min(w[1], nb[1]), max(w[2], nb[2]), max(w[3], nb[3])]
            hit = True
        elif L == "место" and i + 1 < n and _letters(words[i + 1][4]).startswith("печат"):
            nb = words[i + 1]
            box = [min(w[0], nb[0]), min(w[1], nb[1]), max(w[2], nb[2]), max(w[3], nb[3])]
            hit = True
        if hit:
            stamps.append(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, tuple(box)))
            continue
        h = w[3] - w[1]
        if L in ("подпись", "підпис", "подпіс", "signature", "podpis", "unterschrift"):
            # подпись-пометка стоит ПОД линией: расписываются чуть выше неё
            signs.append(((w[0] + w[2]) / 2, w[1] - max(h * 0.9, 2.5 * MM), tuple(w[:4])))
        elif t.count("_") >= 6:
            signs.append(((w[0] + w[2]) / 2, w[1] + h * 0.25, tuple(w[:4])))
    # убрать дубли (одно и то же место, найденное дважды)
    def dedup(items, d):
        out = []
        for it in items:
            if all(abs(it[0] - o[0]) > d or abs(it[1] - o[1]) > d for o in out):
                out.append(it)
        return out
    return dedup(stamps, 6 * MM), dedup(signs, 6 * MM)


def context_text(words, cx, cy, w_mm=55, up_mm=95, down_mm=12):
    """Текст колонки над местом печати — там обычно реквизиты стороны."""
    sel = [w for w in words if abs((w[0] + w[2]) / 2 - cx) <= w_mm * MM
           and cy - up_mm * MM <= (w[1] + w[3]) / 2 <= cy + down_mm * MM]
    return words_to_text(sel)


def _tokens(t):
    return {x for x in re.findall(r"[a-zа-яёіїєґў0-9]{4,}", (t or "").lower())
            if x not in ("печать", "подпись", "штамп", "директор", "компании", "общество")}


def choose_place(cands, words, stamp_name):
    """Какое из нескольких «М.П.» наше: то, рядом с которым написано название печати."""
    if len(cands) <= 1:
        return 0 if cands else None
    want = _tokens(stamp_name)
    if not want:
        return None
    scores = []
    for c in cands:
        ctx = _tokens(context_text(words, c[0], c[1]))
        scores.append(sum(1 for t in want if any(t[:5] == u[:5] for u in ctx)))
    best = max(scores)
    if best > 0 and scores.count(best) == 1:
        return scores.index(best)
    return None


def task_choose_place(cands, words, stamp_name, status=None, cancel=None):
    lines = []
    for n, c in enumerate(cands, 1):
        lines.append(f"Место {n}. Текст рядом:\n{context_text(words, c[0], c[1])[:700]}")
    q = (f"На странице несколько мест для печати («М.П.»). Наша печать называется «{stamp_name}».\n"
         "Определи, к какому месту она относится (чья это сторона договора). Если понять нельзя — 0.\n"
         'Ответ: {"place": номер}\n\n' + "\n\n".join(lines))
    ans, _, _ = chat(sys_prompt(), q, None, 60, status, cancel)
    d = extract_json(ans)
    try:
        k = int(d.get("place") if isinstance(d, dict) else 0)
    except (TypeError, ValueError):
        k = 0
    return k - 1 if 1 <= k <= len(cands) else None


def task_find_places_vision(jpeg, stamp_name="", status=None, cancel=None):
    """Скан без распознанного текста: спросить место у модели со зрением.
    Возвращает ((x, y) печати или None, (x, y) подписи или None) в долях страницы 0..1."""
    q = ("На изображении страница документа. Найди место для печати (надпись «М.П.» или «место печати») "
         "и строку для подписи той же стороны"
         + (f" — стороны, к которой относится печать «{stamp_name}»" if stamp_name else "") + ".\n"
         "Координаты — центр места, в тысячных долях ширины и высоты изображения (0..1000), "
         "x слева направо, y сверху вниз. Если места нет — null.\n"
         'Ответ: {"stamp": [x, y], "sign": [x, y]}')
    ans, _, _ = chat(sys_prompt(), q, [jpeg], 120, status, cancel)
    d = extract_json(ans)

    def pt(v):
        try:
            x, y = float(v[0]), float(v[1])
            if 0 <= x <= 1000 and 0 <= y <= 1000:
                return x / 1000.0, y / 1000.0
        except Exception:
            pass
        return None
    if not isinstance(d, dict):
        return None, None
    return pt(d.get("stamp")), pt(d.get("sign"))


# --------------------------------------------------------------------------- распознавание Windows
_winocr = None


def _winocr_mods():
    global _winocr
    if _winocr is None:
        try:
            if sys.platform != "win32":
                raise ImportError("not windows")
            from winrt.windows.media.ocr import OcrEngine
            from winrt.windows.globalization import Language
            from winrt.windows.graphics.imaging import BitmapDecoder
            from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
            _winocr = {"OcrEngine": OcrEngine, "Language": Language, "BitmapDecoder": BitmapDecoder,
                       "Stream": InMemoryRandomAccessStream, "DataWriter": DataWriter}
        except Exception as e:
            _winocr = {"error": str(e)}
    return _winocr


def win_ocr_languages():
    m = _winocr_mods()
    if "error" in m:
        return []
    try:
        return [str(l.language_tag) for l in m["OcrEngine"].available_recognizer_languages]
    except Exception:
        return []


def win_ocr_available():
    return bool(win_ocr_languages())


def _win_engine(lang=None):
    m = _winocr_mods()
    tags = win_ocr_languages()
    lang = lang or SETTINGS_LOAD().get("ai_ocr_lang") or "auto"
    eng = None
    if lang != "auto":
        pick = [t for t in tags if t.lower().startswith(lang.lower())]
        if pick:
            eng = m["OcrEngine"].try_create_from_language(m["Language"](pick[0]))
    if eng is None:
        for pref in ("ru", "uk", "be"):
            pick = [t for t in tags if t.lower().startswith(pref)]
            if pick and lang == "auto":
                eng = m["OcrEngine"].try_create_from_language(m["Language"](pick[0]))
                if eng is not None:
                    break
    if eng is None:
        eng = m["OcrEngine"].try_create_from_user_profile_languages()
    if eng is None and tags:
        eng = m["OcrEngine"].try_create_from_language(m["Language"](tags[0]))
    if eng is None:
        raise AiError("В Windows не установлен язык распознавания текста.")
    return eng


async def _win_ocr_async(png, lang):
    m = _winocr_mods()
    eng = _win_engine(lang)
    stream = m["Stream"]()
    try:
        writer = m["DataWriter"](stream)
    except TypeError:
        writer = m["DataWriter"](stream.get_output_stream_at(0))
    try:
        writer.write_bytes(png)
    except TypeError:
        writer.write_bytes(list(png))
    await writer.store_async()
    await writer.flush_async()
    try:
        writer.detach_stream()          # чтобы поток не закрылся вместе с writer
    except Exception:
        pass
    stream.seek(0)
    decoder = await m["BitmapDecoder"].create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    res = await eng.recognize_async(bitmap)
    out = []
    for line in res.lines:
        for word in line.words:
            r = word.bounding_rect
            out.append((float(r.x), float(r.y), float(r.x + r.width), float(r.y + r.height), str(word.text)))
    return out


def win_ocr_words(im, lang=None):
    """Распознать картинку средствами Windows. Слова в пикселях картинки.
    Вызывать НЕ из главного потока интерфейса."""
    m = _winocr_mods()
    if "error" in m:
        raise AiError("Распознавание Windows недоступно: " + m["error"])
    import asyncio
    try:
        maxdim = int(m["OcrEngine"].max_image_dimension)
    except Exception:
        maxdim = 10000
    scale = 1.0
    if max(im.size) > maxdim:
        scale = maxdim / max(im.size)
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG")
    box = {}

    def run():
        try:
            try:
                from winrt.runtime import init_apartment, ApartmentType
                init_apartment(ApartmentType.MULTI_THREADED)
            except Exception:
                pass
            box["words"] = asyncio.run(_win_ocr_async(buf.getvalue(), lang))
        except Exception as e:
            box["error"] = e
    if threading.current_thread() is threading.main_thread():
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(120)
        if t.is_alive():
            raise AiError("Распознавание Windows не ответило за 2 минуты.")
    else:
        run()
    if "error" in box:
        raise AiError(f"Распознавание Windows: {box['error']}")
    return [(x0 / scale, y0 / scale, x1 / scale, y1 / scale, t) for x0, y0, x1, y1, t in box.get("words", [])]


def task_ocr_vision(jpeg, status=None, cancel=None):
    """Распознавание через ИИ: строки с рамками в долях 0..1000 → слова-строки в долях 0..1."""
    q = ("Распознай весь текст на изображении страницы, строка за строкой, сверху вниз. "
         "Для каждой строки дай рамку [x0, y0, x1, y1] в тысячных долях ширины и высоты изображения (0..1000). "
         "Текст переписывай точно, ничего не исправляй и не пропускай.\n"
         'Ответ: {"lines": [{"t": "текст строки", "b": [x0, y0, x1, y1]}]}')
    ans, _, _ = chat("Ты система распознавания текста. Отвечай только JSON.", q, [jpeg], 6000, status, cancel)
    d = extract_json(ans)
    out = []
    for r in (d.get("lines") if isinstance(d, dict) else d) or []:
        try:
            t = str(r.get("t") or r.get("text") or "").strip()
            b = [float(v) / 1000.0 for v in (r.get("b") or r.get("box"))[:4]]
            if t and 0 <= b[0] < b[2] <= 1.001 and 0 <= b[1] < b[3] <= 1.001:
                out.append((b[0], b[1], b[2], b[3], t))
        except Exception:
            continue
    if not out:
        raise AiError("ИИ не вернул текст страницы.")
    return out


# --------------------------------------------------------------------------- текстовый слой
_font = None


def _layer_font():
    global _font
    if _font is None:
        for path in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                     "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                     "/System/Library/Fonts/Supplemental/Arial.ttf"):
            if os.path.exists(path):
                try:
                    _font = fitz.Font(fontfile=path)
                    break
                except Exception:
                    pass
        if _font is None:
            try:
                _font = fitz.Font("cjk")
            except Exception:
                _font = fitz.Font("helv")
    return _font


def add_text_layer(page, words):
    """Положить невидимый текст поверх скана. words — в пунктах страницы, как она видна
    (страница должна быть без поворота — см. normalize_rotation). Возвращает число слов."""
    font = _layer_font()
    tw = fitz.TextWriter(page.rect)
    n = 0
    for x0, y0, x1, y1, t in words:
        t = "".join(ch for ch in str(t) if ch.isprintable()).strip()
        w, h = x1 - x0, y1 - y0
        if not t or w <= 0.5 or h <= 0.5:
            continue
        try:
            unit = font.text_length(t, fontsize=1)
            if unit <= 0:
                continue
            fs = max(2.0, min(w / unit, h * 1.6))
            tw.append((x0, y1 - h * 0.22), t, font=font, fontsize=fs)
            n += 1
        except Exception:
            continue
    if n:
        tw.write_text(page, render_mode=3)      # 3 = невидимый: виден только при поиске и выделении
    return n


def normalize_rotation(page):
    """Убрать /Rotate (вид страницы не меняется), чтобы текст лёг ровно."""
    if page.rotation:
        try:
            page.remove_rotation()
        except Exception:
            pass
    try:
        if not page.is_wrapped:
            page.wrap_contents()        # иначе новый текст унаследует чужую матрицу поворота
    except Exception:
        pass
    return page


def selftest_ocr():
    """Для проверки сборки: распознать нарисованную надпись."""
    try:
        if not win_ocr_available():
            m = _winocr_mods()
            return "none" + (":" + m["error"][:80].replace(" ", "_") if "error" in m else "")
        from PIL import ImageDraw, ImageFont
        im = Image.new("RGB", (900, 220), "white")
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.load_default(size=72)
        except TypeError:
            font = ImageFont.load_default()
        d.text((40, 60), "INVOICE 12345", fill="black", font=font)
        words = win_ocr_words(im, "en")
        txt = "".join(w[4] for w in words).replace(" ", "")
        return ("ok:" if "12345" in txt else "bad:") + (txt[:30] or "empty")
    except Exception as e:
        return "fail:" + str(e)[:80].replace(" ", "_")


def hidden_words(page):
    """Слова невидимого (распознанного) слоя — чтобы перенести их на страницу,
    которую превращают в картинку при сведении или сильном сжатии."""
    try:
        if not any(sp.get("type") == 3 for sp in page.get_texttrace()):
            return []
        return page_words(page)
    except Exception:
        return []


def split_pages(doc, max_images=4):
    """Разбить документ на части так, чтобы в одном запросе было не больше max_images сканов
    (большие запросы бесплатные сервисы не принимают)."""
    parts, cur, n = [], [], 0
    for i in range(doc.page_count):
        scan = is_scan_page(doc[i])
        if scan and n >= max_images:
            parts.append(cur)
            cur, n = [], 0
        cur.append(i)
        n += 1 if scan else 0
    if cur:
        parts.append(cur)
    return parts
