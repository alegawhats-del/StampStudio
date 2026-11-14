# -*- coding: utf-8 -*-
"""Инструменты для заполнения документов: регистр текста, конвертеры валют,
сумма прописью в рублях, перевод л.с. ⇄ кВт. Без Qt.

Курсы валют берутся официальные (Нацбанк РБ, api.nbrb.by) — именно они стоят в
таможенных документах; курс можно задать и вручную, и на нужную дату.
"""
import datetime
import json
import re
import urllib.request

import stamp_word as _W

# ---------------------------------------------------------------- регистр текста

def to_upper(s):
    return str(s or "").upper()


def to_lower(s):
    return str(s or "").lower()


def to_title(s):
    """Каждое Слово С Заглавной (дефис и кавычки тоже начинают слово)."""
    return re.sub(r"[^\W\d_]+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), str(s or ""), flags=re.UNICODE)


def to_sentence(s):
    """Как в предложении: первая буква каждого предложения заглавная, остальные строчные."""
    s = str(s or "").lower()
    return re.sub(r"(^|[.!?…]\s+)([^\W\d_])", lambda m: m.group(1) + m.group(2).upper(), s, flags=re.UNICODE)


def to_invert(s):
    """Поменять регистр каждой буквы местами."""
    return str(s or "").swapcase()


CASE_MODES = [("upper", "ВСЕ ЗАГЛАВНЫЕ", to_upper), ("lower", "все строчные", to_lower),
              ("sentence", "Как в предложении", to_sentence), ("title", "Каждое Слово", to_title),
              ("invert", "иНВЕРСИЯ", to_invert)]


# ---------------------------------------------------------------- сумма прописью (рубли)

def rub_in_words(value, currency="RUB"):
    """«49482,39» → «Сорок девять тысяч четыреста восемьдесят два рубля 39 копеек».

    currency: RUB — рубль/копейка, BYN — белорусский рубль/копейка, EUR — евро/цент."""
    parsed = _W.parse_number(value)
    if parsed is None:
        return ""
    rub, kop = parsed
    units = {
        "RUB": (("рубль", "рубля", "рублей"), ("копейка", "копейки", "копеек")),
        "BYN": (("белорусский рубль", "белорусских рубля", "белорусских рублей"),
                ("копейка", "копейки", "копеек")),
        "EUR": (("евро", "евро", "евро"), ("цент", "цента", "центов")),
    }.get(str(currency).upper(), (("рубль", "рубля", "рублей"), ("копейка", "копейки", "копеек")))
    words = _W.number_words(rub, capital=True)
    r_unit = _W._plural(rub, units[0])
    k_unit = _W._plural(kop, units[1])
    return f"{words} {r_unit} {kop:02d} {k_unit}"


# ---------------------------------------------------------------- л.с. ⇄ кВт

HP_TO_KW = 0.735498750

def hp_to_kw(value, decimals=2):
    n = _num(value)
    return "" if n is None else _fmt(n * HP_TO_KW, decimals)


def kw_to_hp(value, decimals=2):
    n = _num(value)
    return "" if n is None else _fmt(n / HP_TO_KW, decimals)


# ---------------------------------------------------------------- валюты

NBRB = "https://api.nbrb.by/exrates/rates/{cur}?parammode=2"
CBR = "https://www.cbr-xml-daily.ru/daily_json.js"


def _nbrb(cur, on_date=None):
    """Официальный курс НБ РБ: (рублей BYN за 1 единицу, дата). on_date — datetime.date."""
    url = NBRB.format(cur=cur)
    if on_date:
        url += "&ondate=%04d-%d-%d" % (on_date.year, on_date.month, on_date.day)
    with urllib.request.urlopen(url, timeout=12) as r:
        d = json.loads(r.read().decode("utf-8"))
    rate = float(d["Cur_OfficialRate"]) / float(d.get("Cur_Scale") or 1)
    return rate, str(d.get("Date", ""))[:10]


def fetch_rates(on_date=None):
    """Официальные курсы на дату (или на сегодня). Возвращает:
        {eur_byn, rub_byn, rub_eur, date, source} — всё в BYN за 1 единицу валюты.
    Бросает RateError, если получить не удалось."""
    try:
        eur_byn, d1 = _nbrb("EUR", on_date)
        rub_byn, d2 = _nbrb("RUB", on_date)
    except Exception as e:
        raise RateError(str(e))
    if eur_byn <= 0 or rub_byn <= 0:
        raise RateError("нулевой курс")
    return {"eur_byn": eur_byn, "rub_byn": rub_byn, "rub_eur": rub_byn / eur_byn,
            "date": d1 or d2, "source": "Нацбанк РБ"}


class RateError(Exception):
    """Не удалось получить курс (нет интернета или сервис недоступен)."""


def convert(amount, rate, decimals=2):
    """Сумма × курс. amount и rate — числа или строки с запятой/точкой."""
    a, r = _num(amount), _num(rate)
    if a is None or r is None:
        return ""
    return _fmt(a * r, decimals)


def percent(part, whole, decimals=2):
    """part / whole × 100 % (жёлтое ÷ синее). «42,62»."""
    p, w = _num(part), _num(whole)
    if p is None or w is None or w == 0:
        return ""
    return _fmt(p / w * 100.0, decimals)


# ---------------------------------------------------------------- числа

def _num(value):
    """«14 587,54» / «14587.54» → float. None, если не число."""
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[\s  ]", "", str(value or "")).replace(",", ".")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", s):
        return None
    return float(s)


def _fmt(n, decimals=2):
    """Число → «14 587,54» (пробел по тысячам, запятая)."""
    s = f"{round(float(n), decimals):,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",")


def fmt_plain(n, decimals=2):
    """Число → «14587.54» (точка, без разделителей) — как в полях ТПО."""
    v = _num(n)
    return "" if v is None else f"{round(v, decimals):.{decimals}f}"


# ---------------------------------------------------------------- самопроверка

def selftest():
    assert to_upper("Молчанов") == "МОЛЧАНОВ" and to_lower("АБВ") == "абв"
    assert to_title("молчанов дмитрий") == "Молчанов Дмитрий"
    assert to_title("мерседес-бенц glb") == "Мерседес-Бенц Glb"
    assert to_sentence("первое. второе предложение") == "Первое. Второе предложение"
    assert to_invert("аБв") == "АбВ"
    assert rub_in_words("49482,39") == "Сорок девять тысяч четыреста восемьдесят два рубля 39 копеек"
    assert rub_in_words("21090.50") == "Двадцать одна тысяча девяносто рублей 50 копеек"
    assert rub_in_words("1,01") == "Один рубль 01 копейка"
    assert rub_in_words("0,00") == "Ноль рублей 00 копеек"
    assert rub_in_words("нет") == ""
    assert rub_in_words("100", "EUR") == "Сто евро 00 центов"
    assert hp_to_kw("249") == "183,14" and kw_to_hp("183.14") == "249,00"
    assert hp_to_kw("бек") == ""
    assert convert("14587.54", "3.392") == "49 480,94"
    assert convert("100", "3,40") == "340,00"
    assert percent("21090.50", "49482.39") == "42,62"
    assert percent("1", "0") == ""
    assert _num("14 587,54") == 14587.54 and _num("14587.54") == 14587.54 and _num("x") is None
    assert fmt_plain("14 587,54") == "14587.54" and _fmt(1234567.8) == "1 234 567,80"
    return True
