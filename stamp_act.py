# -*- coding: utf-8 -*-
"""Акт осмотра автомобиля: заполнение немецкого оригинала и русского перевода из одних данных.

Без Qt. Бланки (.docx) мастерская загружает сама — в программе их нет.
Меняется только текст в известных местах бланка; оформление остаётся как в файле.
"""
import base64
import copy
import io
import math
import os
import random
import re

from stamp_act_assets import LKP, DIAGRAMS

KIT_FILES = {"de": "act_de.docx", "ru": "act_ru.docx"}
KIND_TITLES = [("car", "Легковой"), ("van", "Микроавтобус"), ("pickup", "Пикап")]
FIRST_NUMBER = 4245
GLYPHS_NEED = "0123456789%-/"          # без этих знаков замеры не написать
GLYPHS_MORE = "ABUXWGSC,."             # по желанию: буквы повреждений, запятая и точка
CELL_W = 0.8                            # ширина клетки для образца знака (высота = 1)

# словарь значений: (по-немецки, по-русски)
DICT = {
    "color": [("Schwarz", "Чёрный"), ("Weiß", "Белый"), ("Grau", "Серый"), ("Silber", "Серебристый"),
              ("Blau", "Синий"), ("Dunkelblau", "Тёмно-синий"), ("Rot", "Красный"), ("Grün", "Зелёный"),
              ("Braun", "Коричневый"), ("Beige", "Бежевый"), ("Gelb", "Жёлтый"), ("Orange", "Оранжевый"),
              ("Gold", "Золотистый"), ("Violett", "Фиолетовый"), ("Dunkelgrau", "Тёмно-серый"),
              ("Hellgrau", "Светло-серый"), ("Anthrazit", "Антрацит"), ("Bronze", "Бронзовый")],
    "drive": [("Allradantrieb", "Полный"), ("Frontantrieb", "Передний"), ("Heckantrieb", "Задний")],
    "gear": [("Automatik", "АКПП"), ("Schaltgetriebe", "МКПП"), ("Doppelkupplungsgetriebe", "Робот"),
             ("CVT", "Вариатор")],
    "body": [("Crossover", "Кроссовер"), ("SUV", "Внедорожник"), ("Limousine", "Седан"), ("Kombi", "Универсал"),
             ("Schrägheck", "Хэтчбек"), ("Coupé", "Купе"), ("Cabrio", "Кабриолет"), ("Van", "Минивэн"),
             ("Kleinbus", "Микроавтобус"), ("Pickup", "Пикап"), ("Transporter", "Фургон")],
    "fuel": [("Benzin", "Бензин"), ("Diesel", "Дизель"), ("Benzin/Hybrid", "Бензин/Гибрид"),
             ("Diesel/Hybrid", "Дизель/Гибрид"), ("Plug-in-Hybrid", "Подключаемый гибрид"),
             ("Elektro", "Электро"), ("Gas (LPG)", "Газ")],
}
PAIR_FIELDS = ["color", "drive", "gear", "body", "fuel"]      # у этих полей два значения: _de и _ru
DEFAULT_COMMENT_DE = "Minimale Gebrauchsspuren, dem Alter und der Laufleistung entsprechend."


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower().replace("ё", "е")


def translate(field, value, to):
    """Перевод значения по словарю: to = 'ru' или 'de'. None — в словаре нет."""
    v = _norm(value)
    if not v:
        return ""
    for de, ru in DICT.get(field, []):
        if to == "ru" and _norm(de) == v:
            return ru
        if to == "de" and _norm(ru) == v:
            return de
    return None


def group_digits(s):
    """«53997» → «53 997»; нецифровое остаётся как есть."""
    d = re.sub(r"\D", "", str(s or ""))
    if not d:
        return str(s or "").strip()
    return re.sub(r"(?<=\d)(?=(\d{3})+$)", " ", d)


def clean_vin(s):
    return re.sub(r"[^A-Za-z0-9]", "", str(s or "")).upper()[:17]


def vin_problem(s):
    """Почему VIN выглядит неверно ('' — всё в порядке)."""
    v = clean_vin(s)
    if not v:
        return "VIN не заполнен"
    if len(v) != 17:
        return f"в VIN {len(v)} знаков вместо 17"
    bad = sorted(set(ch for ch in v if ch in "IOQ"))
    if bad:
        return "в VIN не бывает букв " + ", ".join(bad)
    return ""


def volume_de(liters, ccm):
    l_ = str(liters or "").strip().replace(",", ".")
    c = group_digits(ccm) if re.sub(r"\D", "", str(ccm or "")) else ""
    if l_ and c:
        return f"{l_} ({c} cm³)"
    return l_ or (f"{c} cm³" if c else "")


def volume_ru(liters, ccm):
    l_ = str(liters or "").strip().replace(",", ".")
    if l_:
        return f"{l_} л"
    c = group_digits(ccm) if re.sub(r"\D", "", str(ccm or "")) else ""
    return f"{c} см³" if c else ""


# ---------------------------------------------------------------- работа с .docx

def _docx():
    import docx
    return docx


def _runs(par):
    return [r for r in par._p if r.tag.endswith("}r")]


def _set_par(par, text, keep=0):
    """Текст абзаца: первые keep фрагментов не трогаем, в следующий пишем text, остальные убираем.
    Оформление берётся у того фрагмента, в который пишем."""
    runs = _runs(par)
    if len(runs) <= keep:
        par.add_run(text)
        return
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    tgt = runs[keep]
    for ch in list(tgt):
        if ch.tag != W + "rPr":
            tgt.remove(ch)
    t = tgt.makeelement(W + "t", {})
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    tgt.append(t)
    for r in runs[keep + 1:]:
        par._p.remove(r)


def _set_cell(cell, text, par=0):
    ps = cell.paragraphs
    while len(ps) <= par:
        cell.add_paragraph("")
        ps = cell.paragraphs
    _set_par(ps[par], text)


def _find_table(doc, first_cell_starts):
    for t in doc.tables:
        try:
            if _norm(t.cell(0, 0).text).startswith(_norm(first_cell_starts)):
                return t
        except Exception:
            continue
    return None


def _find_par(doc, starts):
    for p in doc.paragraphs:
        if _norm(p.text).startswith(_norm(starts)):
            return p
    return None


def _row_cells(row):
    out, seen = [], set()
    for c in row.cells:
        if id(c._tc) not in seen:
            seen.add(id(c._tc))
            out.append(c)
    return out


def _value_after(table, label):
    """Ячейка со значением: следующая после ячейки с подписью label."""
    for row in table.rows:
        cells = _row_cells(row)
        for i, c in enumerate(cells[:-1]):
            if _norm(c.text) == _norm(label):
                return cells[i + 1]
    return None


def check_templates(de_path, ru_path):
    """Подходят ли бланки: список того, что не найдено (пустой — всё на месте)."""
    docx = _docx()
    miss = []
    try:
        d = docx.Document(de_path)
        for what, ok in (("строка «INSPEKTIONSBERICHT №»", _find_par(d, "INSPEKTIONSBERICHT")),
                         ("таблица «Datum»", _find_table(d, "Datum")),
                         ("таблица «Name der Organisation»", _find_table(d, "Name der Organisation")),
                         ("таблица «Marke»", _find_table(d, "Marke")),
                         ("таблица «Kraftstoff»", _find_table(d, "Kraftstoff")),
                         ("таблица «Reifen»", _find_table(d, "Reifen")),
                         ("клетки VIN", _vin_table(d)),
                         ("схема автомобиля", _diagram_part(d))):
            if ok is None:
                miss.append("оригинал: " + what)
    except Exception as e:
        miss.append(f"оригинал не читается: {e}")
    try:
        r = docx.Document(ru_path)
        for what, ok in (("таблица «Номер документа»", _find_table(r, "Номер документа")),
                         ("таблица «Марка»", _find_table(r, "Марка"))):
            if ok is None:
                miss.append("перевод: " + what)
    except Exception as e:
        miss.append(f"перевод не читается: {e}")
    return miss


def _vin_table(doc):
    for t in doc.tables:
        try:
            if len(t.rows) == 1 and len(_row_cells(t.rows[0])) == 17:
                return t
        except Exception:
            continue
    return None


def _diagram_part(doc):
    """Картинка схемы в оригинале: самая широкая вставленная картинка."""
    best = None
    for el in doc.element.body.iter():
        if not el.tag.endswith("}inline") and not el.tag.endswith("}anchor"):
            continue
        ext = [x for x in el.iter() if x.tag.endswith("}extent")]
        blip = [x for x in el.iter() if x.tag.endswith("}blip")]
        if not ext or not blip:
            continue
        cx, cy = int(ext[0].get("cx", 0)), int(ext[0].get("cy", 0))
        rid = blip[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
        if rid and cy and 1.6 < cx / cy < 2.4 and (best is None or cx > best[0]):
            best = (cx, rid)
    if best is None:
        return None
    try:
        return doc.part.related_parts[best[1]]
    except Exception:
        return None


def diagram_png(kind):
    return base64.b64decode(DIAGRAMS.get(kind) or DIAGRAMS["car"])


def _tire_runs(par_runs):
    """Образцы: обычный фрагмент текста и фрагмент с галочкой (картинкой)."""
    plain = draw = None
    for r in par_runs:
        has_draw = any(x.tag.endswith("}drawing") or x.tag.endswith("}pict") for x in r.iter())
        has_text = any(x.tag.endswith("}t") for x in r)
        if has_draw and draw is None:
            draw = r
        if has_text and not has_draw and plain is None:
            plain = r
    return plain, draw


def _fill_tires(cell, tires):
    """Резина: Sommer / Winter / Ganzjahresreifen — галочка и марка, либо «___»."""
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    pars = cell.paragraphs
    p_sw = next((p for p in pars if _norm(p.text).startswith("sommer")), None)
    p_all = next((p for p in pars if _norm(p.text).startswith("ganzjahres")), None)
    if p_sw is None:
        return
    plain, draw = _tire_runs(_runs(p_sw))
    if plain is None:
        return

    def text_run(text):
        r = copy.deepcopy(plain)
        for ch in list(r):
            if ch.tag != W + "rPr":
                r.remove(ch)
        t = r.makeelement(W + "t", {})
        t.text = text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t)
        return r

    def line(par, label, key):
        on = bool((tires.get(key) or {}).get("on"))
        brand = str((tires.get(key) or {}).get("brand") or "").strip()
        par.append(text_run(label + (f" ({brand})" if brand else "") + " "))
        if on and draw is not None:
            par.append(copy.deepcopy(draw))
        elif on:
            par.append(text_run("✓"))
        else:
            par.append(text_run("___"))

    for r in _runs(p_sw):
        p_sw._p.remove(r)
    line(p_sw._p, "Sommer", "summer")
    br = copy.deepcopy(plain)
    for ch in list(br):
        if ch.tag != W + "rPr":
            br.remove(ch)
    br.append(br.makeelement(W + "br", {}))
    p_sw._p.append(br)
    line(p_sw._p, "Winter", "winter")
    if p_all is not None:
        for r in _runs(p_all):
            p_all._p.remove(r)
        line(p_all._p, "Ganzjahresreifen", "all")


def fill_de(template, data, out_path):
    """Немецкий оригинал. data — словарь из form_data(); возвращает out_path."""
    docx = _docx()
    d = docx.Document(template)
    p = _find_par(d, "INSPEKTIONSBERICHT")
    if p is not None:
        rs = _runs(p)
        _set_par(p, str(data.get("number", "")), keep=max(0, len(rs) - 1))
    t = _find_table(d, "Datum")
    if t is not None:
        _set_cell(_row_cells(t.rows[0])[-1], data.get("date", ""))
    t = _find_table(d, "Name der Organisation")
    if t is not None:
        _set_cell(_row_cells(t.rows[0])[-1], data.get("master", ""))
    t = _find_table(d, "Marke")
    if t is not None:
        for label, key in (("Marke", "brand"), ("Model", "model"), ("Baujahr des Fahrzeugs", "year"),
                           ("Farbe", "color_de"), ("Antrieb", "drive_de"), ("Getriebe", "gear_de"),
                           ("Karosserietyp", "body_de"), ("Anzahl der Sitzplätze", "seats"),
                           ("Anzahl der Türen", "doors")):
            c = _value_after(t, label)
            if c is not None:
                _set_cell(c, str(data.get(key, "")))
    p = _find_par(d, "Anzahl der Eigentümer")
    if p is not None:
        _set_par(p, str(data.get("owners", "") or "1"), keep=max(0, len(_runs(p)) - 1))
    p = _find_par(d, "Kilometerstand")
    if p is not None:
        rs = _runs(p)
        keep = 3 if len(rs) > 3 else max(0, len(rs) - 1)
        _set_par(p, (group_digits(data.get("mileage", "")) + " km").strip(), keep=keep)
    t = _vin_table(d)
    if t is not None:
        vin = clean_vin(data.get("vin", ""))
        for i, c in enumerate(_row_cells(t.rows[0])):
            _set_cell(c, vin[i] if i < len(vin) else "")
    t = _find_table(d, "Kraftstoff")
    if t is not None:
        for label, val in (("Kraftstoff", data.get("fuel_de", "")),
                           ("Hubraum", volume_de(data.get("liters"), data.get("ccm"))),
                           ("Anzahl der PS.", str(data.get("hp", "")))):
            c = _value_after(t, label)
            if c is not None:
                _set_cell(c, val)
    t = _find_table(d, "Reifen")
    if t is not None:
        _fill_tires(t.cell(0, 0), data.get("tires") or {})
        try:
            _set_cell(t.cell(0, 1), data.get("comment_de") or "-", par=1)
            _set_cell(t.cell(len(t.rows) - 1, 1), data.get("start_de") or "-", par=1)
        except Exception:
            pass
    part = _diagram_part(d)
    if part is not None:
        part._blob = diagram_png(data.get("kind", "car"))
    d.save(out_path)
    return out_path


def ru_sections(template):
    """Тексты русского акта, которые можно править: [{idx, title, text}] — абзацы после заголовков разделов."""
    docx = _docx()
    r = docx.Document(template)
    out, title, started = [], "", False
    for i, p in enumerate(r.paragraphs):
        t = p.text.strip()
        if not t:
            continue
        if re.match(r"^\d+\.\s", t) or _norm(t) == "заключение":
            n = int(re.match(r"^(\d+)", t).group(1)) if t[0].isdigit() else 99
            started = started or n >= 3
            title = t
            continue
        if started:
            out.append({"idx": i, "title": title, "text": t})
    return out


def fill_ru(template, data, out_path, texts=None):
    """Русский перевод: табличка первой страницы и (если правили) тексты разделов. texts: {idx: текст}."""
    docx = _docx()
    r = docx.Document(template)
    t = _find_table(r, "Номер документа")
    if t is not None:
        for label, val in (("Номер документа", str(data.get("number", ""))), ("Дата", data.get("date", ""))):
            c = _value_after(t, label)
            if c is not None:
                _set_cell(c, val)
    t = _find_table(r, "Марка")
    if t is not None:
        km = group_digits(data.get("mileage", ""))
        hp = str(data.get("hp", "")).strip()
        for label, val in (("Марка", data.get("brand", "")), ("Модель", data.get("model", "")),
                           ("Год выпуска", str(data.get("year", ""))), ("Цвет", data.get("color_ru", "")),
                           ("Привод", data.get("drive_ru", "")), ("Коробка передач", data.get("gear_ru", "")),
                           ("Тип кузова", data.get("body_ru", "")), ("Количество сидений", str(data.get("seats", ""))),
                           ("Количество дверей", str(data.get("doors", ""))),
                           ("Количество владельцев", str(data.get("owners", "") or "1")),
                           ("Пробег", f"{km} км" if km else ""), ("VIN", clean_vin(data.get("vin", ""))),
                           ("Тип топлива", data.get("fuel_ru", "")),
                           ("Объём двигателя", volume_ru(data.get("liters"), data.get("ccm"))),
                           ("Мощность", f"{hp} л. с." if hp else "")):
            c = _value_after(t, label)
            if c is not None:
                _set_cell(c, str(val))
    pars = r.paragraphs
    for idx, text in (texts or {}).items():
        try:
            p = pars[int(idx)]
            if p.text.strip() != str(text).strip():
                _set_par(p, str(text).strip())
        except Exception:
            continue
    r.save(out_path)
    return out_path


# ---------------------------------------------------------------- почерк мастера

def glyphs_missing(text, glyphs):
    """Каких знаков из text нет в почерке мастера."""
    return sorted(set(ch for ch in str(text) if ch != " " and not (glyphs or {}).get(ch)))


def hand_layout(text, glyphs, height, seed=0, pen=None):
    """Разложить строку почерком мастера. Возвращает (штрихи, ширина, высота):
    штрихи — [[(x, y, толщина), …], …] в пикселях. Каждый раз чуть иначе, как у живой руки."""
    rnd = random.Random(seed)
    pen_w = float(pen or max(1.0, height * 0.062))
    strokes, x = [], height * 0.12
    slant = rnd.uniform(-0.03, 0.03)
    for ch in str(text):
        if ch == " ":
            x += height * 0.32
            continue
        g = (glyphs or {}).get(ch)
        if not g:
            continue
        xs = [p[0] for st in g for p in st]
        ys = [p[1] for st in g for p in st]
        if not xs:
            continue
        gx0, gx1, gy0, gy1 = min(xs), max(xs), min(ys), max(ys)
        sc = height * rnd.uniform(0.95, 1.05)
        ang = rnd.uniform(-0.035, 0.035) + slant
        ca, sa = math.cos(ang), math.sin(ang)
        cx, cy = (gx0 + gx1) / 2, (gy0 + gy1) / 2
        dy = height * rnd.uniform(-0.035, 0.035)
        w = pen_w * rnd.uniform(0.92, 1.08)
        for st in g:
            pts = []
            for px, py in st:
                ux, uy = (px - cx) * sc, (py - cy) * sc
                rx, ry = ux * ca - uy * sa, ux * sa + uy * ca
                pts.append((x + (gx1 - gx0) * sc / 2 + rx, cy * height + dy + ry, w))
            if pts:
                strokes.append(pts)
        x += (gx1 - gx0) * sc + height * rnd.uniform(0.07, 0.13)
    return strokes, x + height * 0.05, height * 1.1


def lkp_places(page_rect_of_diagram, kind):
    """Окошки и колёса на странице PDF: [(имя, x0, y0, x1, y1)] по прямоугольнику схемы (x0, y0, x1, y1)."""
    X0, Y0, X1, Y1 = page_rect_of_diagram
    w, h = X1 - X0, Y1 - Y0
    m = LKP.get(kind) or LKP["car"]
    out = []
    for i, b in enumerate(m["boxes"]):
        out.append((f"b{i + 1}", X0 + b[0] * w, Y0 + b[1] * h, X0 + b[2] * w, Y0 + b[3] * h))
    for i, b in enumerate(m["wheels"]):
        out.append((f"w{i + 1}", X0 + b[0] * w, Y0 + b[1] * h, X0 + b[2] * w, Y0 + b[3] * h))
    return out


def find_diagram(pdf_doc):
    """Где в PDF лежит схема: (номер страницы, (x0, y0, x1, y1)) или None."""
    best = None
    for i in range(pdf_doc.page_count):
        try:
            infos = pdf_doc[i].get_image_info()
        except Exception:
            continue
        for im in infos:
            x0, y0, x1, y1 = im["bbox"]
            w, h = x1 - x0, y1 - y0
            if h > 0 and w > 250 and 1.6 < w / h < 2.4 and (best is None or w > best[2]):
                best = (i, (x0, y0, x1, y1), w)
    return (best[0], best[1]) if best else None


# ---------------------------------------------------------------- перевод через ИИ

AI_SYSTEM = ("Ты переводчик автомобильных актов осмотра. Переводи точно и коротко, термины — как принято "
             "в автосервисе. Ничего не добавляй от себя. Ответ — только JSON-массив строк той же длины, "
             "в том же порядке, без пояснений.")


def ai_translate(texts, to, chat, status=None, cancel=None):
    """Перевести список строк на to ('ru' / 'de') через ИИ. chat — функция stamp_ai.chat."""
    import json
    texts = [str(t) for t in texts]
    if not any(t.strip() for t in texts):
        return list(texts)
    lang = "русский" if to == "ru" else "немецкий"
    ask = f"Переведи на {lang} каждую строку массива:\n" + json.dumps(texts, ensure_ascii=False)
    ans, _prov, _model = chat(AI_SYSTEM, ask, max_tokens=1500, status=status, cancel=cancel)
    m = re.search(r"\[.*\]", ans or "", re.S)
    if not m:
        raise ValueError("ИИ ответил не списком — попробуйте ещё раз")
    out = json.loads(m.group(0))
    if not isinstance(out, list) or len(out) != len(texts):
        raise ValueError("ИИ вернул другое число строк — попробуйте ещё раз")
    return [str(x).strip() for x in out]


# ---------------------------------------------------------------- самопроверка

def selftest():
    """Проверка без бланков: словарь, форматы, почерк, схемы."""
    assert translate("color", "grau", "ru") == "Серый" and translate("gear", "акпп", "de") == "Automatik"
    assert translate("color", "небесный", "de") is None and translate("fuel", "", "ru") == ""
    assert group_digits("53997") == "53 997" and group_digits("1598") == "1 598" and group_digits("997") == "997"
    assert volume_de("1,6", "1598") == "1.6 (1 598 cm³)" and volume_ru("1.6", "1598") == "1.6 л"
    assert clean_vin("u5yp-v81g bpl097231") == "U5YPV81GBPL097231" and not vin_problem("U5YPV81GBPL097231")
    assert vin_problem("U5YPV81GBPL09723") and vin_problem("O5YPV81GBPL097231")
    for kind, _ in KIND_TITLES:
        assert len(LKP[kind]["boxes"]) == 17 and len(LKP[kind]["wheels"]) == 4
        assert diagram_png(kind)[:4] == b"\x89PNG"
    g = {"1": [[(0.4, 0.1), (0.4, 0.9)]], "2": [[(0.2, 0.2), (0.6, 0.2), (0.2, 0.9), (0.6, 0.9)]]}
    st, w, h = hand_layout("121", g, 40, seed=3)
    st2, _, _ = hand_layout("121", g, 40, seed=4)
    assert len(st) == 3 and w > 20 and st != st2 and glyphs_missing("12%", g) == ["%"]
    assert len(lkp_places((0, 0, 200, 100), "van")) == 21
    return True
