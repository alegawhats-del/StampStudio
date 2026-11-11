# -*- coding: utf-8 -*-
"""Заполнение документов Word (.docx) без поломки вёрстки.

Меняется только текст внутри уже существующих фрагментов: шрифты, отступы, таблицы, нумерация,
колонтитулы и разрывы остаются как были. Модуль не зависит от Qt.

  doc = WordDoc(path)
  doc.fields   — найденные места для заполнения (прочерки, даты, суммы прописью, пустые ячейки таблиц)
  doc.dummies  — «образцы» вроде «Иванов Иван Иванович», «00 00 000000», «БМ-000» со счётчиком повторов
  doc.paragraphs_text() — весь текст по абзацам (для свободной правки)
  doc.save(out_path, values, replaces, edits)
"""
import copy
import re

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML = "http://www.w3.org/XML/1998/namespace"
T, P, R, TC, TR, TBL, RPR, PPR = (f"{{{W}}}{n}" for n in ("t", "p", "r", "tc", "tr", "tbl", "rPr", "pPr"))

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
          "октября", "ноября", "декабря")

# ----------------------------------------------------------------------------- число прописью
_ONES_M = ("", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_ONES_F = ("", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_TEENS = ("десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
          "семнадцать", "восемнадцать", "девятнадцать")
_TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто")
_HUNS = ("", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот")
_SCALE = ((("тысяча", "тысячи", "тысяч"), True), (("миллион", "миллиона", "миллионов"), False),
          (("миллиард", "миллиарда", "миллиардов"), False))


def _plural(n, forms):
    n = abs(n) % 100
    if 10 < n < 20:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else (forms[1] if 2 <= n <= 4 else forms[2])


def _triple(n, fem):
    out = [_HUNS[n // 100]]
    n %= 100
    if 10 <= n < 20:
        out.append(_TEENS[n - 10])
    else:
        out.append(_TENS[n // 10])
        out.append((_ONES_F if fem else _ONES_M)[n % 10])
    return [w for w in out if w]


def number_words(n, capital=True):
    """1992000 → «Один миллион девятьсот девяносто две тысячи»."""
    n = int(n)
    if n == 0:
        words = ["ноль"]
    else:
        words, groups, i = [], [], 0
        while n:
            groups.append(n % 1000)
            n //= 1000
        for i in range(len(groups) - 1, -1, -1):
            g = groups[i]
            if not g:
                continue
            if i == 0:
                words += _triple(g, False)
            else:
                forms, fem = _SCALE[min(i - 1, 2)]
                words += _triple(g, fem) + [_plural(g, forms)]
    s = " ".join(words)
    return s[:1].upper() + s[1:] if capital else s


def parse_number(text):
    """«1 992 000,50» → (1992000, 50). None, если это не число."""
    s = re.sub(r"[\s  ]", "", str(text or "")).replace(".", ",")
    m = re.fullmatch(r"(\d+)(?:,(\d{1,2}))?", s)
    if not m:
        return None
    return int(m.group(1)), int((m.group(2) or "0").ljust(2, "0"))


def format_number(n, sep=" "):
    s = str(int(n))
    parts = []
    while s:
        parts.insert(0, s[-3:])
        s = s[:-3]
    return sep.join(parts)


def parse_date(text):
    """«11.11.2026», «11/11/26», «11 ноября 2026» → (11, 11, 2026) или None."""
    s = str(text or "").strip().lower()
    m = re.fullmatch(r"(\d{1,2})[./\-\s](\d{1,2})[./\-\s](\d{2,4})\s*(?:г\.?|года)?", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"«?(\d{1,2})»?\s+([а-яё]+)\s+(\d{4})\s*(?:г\.?|года)?", s)
        if not m:
            return None
        stem = m.group(2)[:3]
        mo = next((i + 1 for i, name in enumerate(MONTHS) if name.startswith(stem)), 0)
        d, y = int(m.group(1)), int(m.group(3))
    if y < 100:
        y += 2000
    return (d, mo, y) if 1 <= d <= 31 and 1 <= mo <= 12 else None


def initials(fio):
    """«Ефименко Александр Иванович» → «Ефименко А. И.»"""
    parts = str(fio or "").split()
    if len(parts) < 2:
        return ""
    return parts[0] + " " + " ".join(p[0].upper() + "." for p in parts[1:3])


# ----------------------------------------------------------------------------- шаблоны поиска
RE_DATE = re.compile(r"«\s*[_0]{1,4}\s*»\s*[_]{2,}(?:\s*(\d{4}))?(?:\s*(г\.|года|год))?")
RE_SUM = re.compile(r"(?<![\d,.])(\d[\d  ]*?)(,\d{2})?\s*\(\s*([^()\d]{0,160}?)\s*\)")
RE_BLANK = re.compile(r"_{3,}")
RE_INITIALS = re.compile(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.")
DUMMY_PATTERNS = (
    ("ФИО", r"Иванов(?:а)? Иван(?:а)? Иванович(?:а)?"),
    ("ФИО коротко", r"Иванов(?:а)? И\.\s?И\."),
    ("Паспорт", r"\b00 00 000000\b"),
    ("Дата", r"\b0[01]\.0[01]\.(?:0000|2000)\b"),
    ("Телефон", r"\+7\s?\(000\)\s?000-00-00"),
    ("Номер договора", r"\b[А-ЯЁA-Z]{1,4}-(?:000|_{2,})(?![\d_])"),
    ("Номер договора", r"\b000[–-]20\d\d\b"),
)


class Field:
    """Одно место для заполнения. kind: blank | date | sum | cell | tail."""

    def __init__(self, kind, par, start, end, label, current="", meta=None):
        self.kind, self.par, self.start, self.end = kind, par, start, end
        self.label, self.current, self.meta = label, current, meta or {}

    def render(self, value):
        """Текст, который встанет на место фрагмента; None — оставить как есть."""
        value = str(value or "").strip()
        if not value:
            return None
        if self.kind == "date":
            d = parse_date(value)
            if not d:
                return value
            tail = self.meta.get("tail") or ""
            return f"«{d[0]:02d}» {MONTHS[d[1] - 1]} {d[2]}" + (f" {tail}" if tail else "")
        if self.kind == "sum":
            num = parse_number(value)
            if not num:
                return value
            whole, frac = num
            words = number_words(whole, capital=self.meta.get("capital", True))
            dec = f",{frac:02d}" if self.meta.get("decimals") else ""
            return f"{format_number(whole, self.meta.get('sep', ' '))}{dec} ({words})"
        if self.kind == "tail":
            return " " + value
        return value


class WordDoc:
    def __init__(self, path):
        import docx                                   # python-docx (lxml): сохраняет файл без потерь
        self.path = path
        self.doc = docx.Document(path)
        self.pars = [p for p in self.doc.element.body.iter(P)]
        self.zones = []                               # [(название, элемент, [номера абзацев])] — колонтитулы
        seen = set()
        for sec in self.doc.sections:
            parts = [("Верхний колонтитул", "header"), ("Нижний колонтитул", "footer")]
            try:
                if sec.different_first_page_header_footer:
                    parts += [("Верхний колонтитул первой страницы", "first_page_header"),
                              ("Нижний колонтитул первой страницы", "first_page_footer")]
            except Exception:
                pass
            for title, attr in parts:
                try:
                    part = getattr(sec, attr)
                    if part.is_linked_to_previous:
                        continue
                    el = part._element
                except Exception:
                    continue
                if id(el) in seen:
                    continue
                seen.add(id(el))
                ps = [p for p in el.iter(P)]
                if not any("".join(t.text or "" for t in p.iter(T)).strip() for p in ps):
                    continue                           # пустой колонтитул не показываем
                start = len(self.pars)
                self.pars += ps
                self.zones.append((title, el, list(range(start, start + len(ps)))))
        self._texts = [self._ts(p) for p in self.pars]
        self.fields = self._find_fields()
        self.dummies = self._find_dummies()

    # ---- текст абзаца: только его собственные w:t (вложенные надписи считаются отдельными абзацами)
    @staticmethod
    def _ts(p):
        out = []
        for t in p.iter(T):
            a = t.getparent()
            while a is not None and a.tag != P:
                a = a.getparent()
            if a is p:
                out.append(t)
        return out

    def text(self, i):
        return "".join(t.text or "" for t in self._texts[i])

    def _cell_ctx(self, p):
        """(текст предыдущих ячеек строки, номер ячейки, число ячеек, абзацы той же ячейки)."""
        a = p.getparent()
        while a is not None and a.tag != TC:
            a = a.getparent()
        if a is None:
            return "", -1, 0, []
        tr = a.getparent()
        cells = [c for c in tr if c.tag == TC]
        idx = cells.index(a)
        prev = " ".join("".join(t.text or "" for t in c.iter(T)).strip() for c in cells[:idx])
        return re.sub(r"\s+", " ", prev).strip(), idx, len(cells), [x for x in a.iter(P)]

    @staticmethod
    def _snip(text, a, b, kind):
        left = re.sub(r"\s+", " ", text[max(0, a - 70):a]).lstrip()
        if len(text[:a]) > 70 and " " in left:
            left = "…" + left.split(" ", 1)[1]
        right = re.sub(r"\s+", " ", text[b:b + 28]).rstrip()
        if len(text) > b + 28:
            right = right.rsplit(" ", 1)[0] + "…"
        mark = {"date": "[дата]", "sum": "[сумма]"}.get(kind, "[   ]")
        left, right = re.sub(r"_{4,}", "___", left), re.sub(r"_{4,}", "___", right)
        return f"{left}{mark}{right}".strip()

    def _find_fields(self):
        out = []
        for i, p in enumerate(self.pars):
            text = self.text(i)
            if not text.strip():
                ctx, idx, n, _ = self._cell_ctx(p)
                # пустая ячейка-значение в таблице «№ | название | значение»
                if idx >= 1 and 2 <= n <= 4 and idx == n - 1 and 2 <= len(ctx) <= 110 and not re.search(r"_|/\s*$", ctx):
                    cell = p.getparent()
                    first = [x for x in cell.iter(P)][0]
                    whole = "".join(t.text or "" for t in cell.iter(T)).strip()
                    if first is p and not whole and (n == 2 or re.match(r"^\d+\.?\s", ctx + " ")):
                        out.append(Field("cell", i, 0, 0, re.sub(r"^\d+\.?\s+", "", ctx)))
                continue
            taken = []
            for m in RE_DATE.finditer(text):
                out.append(Field("date", i, m.start(), m.end(), self._snip(text, m.start(), m.end(), "date"),
                                 meta={"tail": m.group(2) or ""}))
                taken.append(m.span())
            for m in RE_SUM.finditer(text):
                words = m.group(3)
                blank = bool(re.fullmatch(r"[_\s.]*", words))
                digits = re.sub(r"[  ]", "", m.group(1))
                if not blank and not re.search(r"[а-яё]{3,}", words.lower()):
                    continue
                if not blank and number_words(int(digits)).lower() != re.sub(r"\s+", " ", words.strip().lower()):
                    continue                           # в скобках не это число прописью — не трогаем
                zero = set(digits) <= {"0"}
                ctx = self._cell_ctx(p)[0]
                label = self._snip(text, m.start(), m.end(), "sum")
                if ctx and len(text) < 90:
                    label = re.sub(r"^\d+\.?\s+", "", ctx) + ": " + label
                out.append(Field("sum", i, m.start(), m.end(), label,
                                 current="" if zero else format_number(int(digits)) + (m.group(2) or ""),
                                 meta={"decimals": bool(m.group(2)), "capital": blank or words.strip()[:1].isupper(),
                                       "sep": " " if " " in m.group(1) else " "}))
                taken.append(m.span())
            ctx, idx, n, cell_pars = self._cell_ctx(p)
            for m in RE_BLANK.finditer(text):
                if any(a <= m.start() < b for a, b in taken):
                    continue
                before, after = text[:m.start()].rstrip(), text[m.end():].lstrip()
                if (before.endswith("/") and (after.startswith("/") or not after)) or (not before and after.startswith("/")):
                    continue                           # «/ ________ /» — место для подписи
                if not before and not after and cell_pars:
                    k = cell_pars.index(p)
                    prev_t = "".join(t.text or "" for t in cell_pars[k - 1].iter(T)) if k else ""
                    if RE_INITIALS.search(prev_t) or "подпис" in prev_t.lower() or "/" in prev_t:
                        continue                       # строка под фамилией — тоже подпись
                label = self._snip(text, m.start(), m.end(), "blank")
                if ctx and len(before) < 3 and len(ctx) <= 60:
                    label = re.sub(r"^\d+\.?\s+", "", ctx) + " " + label
                out.append(Field("blank", i, m.start(), m.end(), label))
            if cell_pars and len(text.strip()) <= 42 and text.rstrip().endswith(":") and not text.strip().isupper():
                out.append(Field("tail", i, len(text.rstrip()), len(text), text.strip()))
            elif (not any(f.par == i for f in out) and idx >= 1 and 2 <= n <= 4 and idx == n - 1 and len(cell_pars) == 1
                  and len(text) <= 120 and guess_label(ctx) and re.match(r"^\d+\.?\s", ctx + " ")
                  and not any(re.search(pat, text) for _n, pat in DUMMY_PATTERNS)):
                out.append(Field("cell", i, 0, len(text), re.sub(r"^\d+\.?\s+", "", ctx), current=text.strip()))
        out.sort(key=lambda f: (f.par, f.start))
        for f in out:
            p = self.pars[f.par]
            ctx = self._cell_ctx(p)[0]
            f.meta["ctx"] = re.sub(r"^\d+\.?\s+", "", ctx)
            a = p.getparent()
            while a is not None and a.tag != TBL:
                a = a.getparent()
            f.meta["table"] = a.getroottree().getpath(a) if a is not None else ""
        for f in out:                                  # подпись без слов («[дата]») — добавить, что стоит перед ней
            if not re.search(r"[A-Za-zА-Яа-яЁё]{2,}", re.sub(r"\[[^\]]*\]", "", f.label)):
                j = f.par - 1
                while j >= 0 and not self.text(j).strip():
                    j -= 1
                if j >= 0:
                    prev = re.sub(r"\s+", " ", self.text(j)).strip()
                    f.label = (prev[:48] + ("…" if len(prev) > 48 else "")) + "  →  " + f.label
        return out

    def _find_dummies(self):
        """[(название, текст-образец, сколько раз встречается)] — в порядке появления."""
        full = [self.text(i) for i in range(len(self.pars))]
        seen, out = {}, []
        for name, pat in DUMMY_PATTERNS:
            rx = re.compile(pat)
            for t in full:
                for m in rx.finditer(t):
                    s = m.group(0)
                    if s not in seen:
                        seen[s] = [name, s, 0]
                        out.append(seen[s])
                    seen[s][2] += 1
        return [tuple(x) for x in out]

    def paragraphs_text(self):
        """[(номер абзаца, текст)] — только непустые."""
        return [(i, self.text(i)) for i in range(len(self.pars)) if self.text(i).strip()]

    # ---- запись
    def _replace_span(self, i, start, end, new):
        ts = self._texts[i]
        if not ts:
            self._append_run(i, new)
            return
        pos, placed = 0, False
        for t in ts:
            s = t.text or ""
            a, b = pos, pos + len(s)
            pos = b
            if b < start or a > end or (a == end and placed) or (b == start and b != a and start != end and t is not ts[-1]):
                continue
            lo, hi = max(start, a) - a, min(end, b) - a
            if not placed:
                t.text = s[:lo] + new + s[hi:]
                placed = True
            else:
                t.text = s[:lo] + s[hi:]
            t.set(f"{{{XML}}}space", "preserve")
        if not placed:
            last = ts[-1]
            last.text = (last.text or "") + new
            last.set(f"{{{XML}}}space", "preserve")

    def _append_run(self, i, text):
        p = self.pars[i]
        r = p.makeelement(R, {})
        ppr = p.find(PPR)
        if ppr is not None and ppr.find(RPR) is not None:
            r.append(copy.deepcopy(ppr.find(RPR)))
        t = p.makeelement(T, {f"{{{XML}}}space": "preserve"})
        t.text = text
        r.append(t)
        p.append(r)
        self._texts[i] = [t]

    def _set_text(self, i, new):
        """Заменить текст абзаца целиком, сохранив оформление: меняется только отличающаяся середина."""
        old = self.text(i)
        if old == new:
            return
        a = 0
        while a < min(len(old), len(new)) and old[a] == new[a]:
            a += 1
        b = 0
        while b < min(len(old), len(new)) - a and old[len(old) - 1 - b] == new[len(new) - 1 - b]:
            b += 1
        self._replace_span(i, a, len(old) - b, new[a:len(new) - b])

    def apply(self, values=None, replaces=None, edits=None):
        """values: {номер поля: текст}; replaces: [(что, на что)]; edits: {номер абзаца: новый текст}."""
        values, replaces, edits = values or {}, replaces or [], edits or {}
        done = 0
        by_par = {}
        for k, f in enumerate(self.fields):
            new = f.render(values.get(k))
            if new is not None and f.par not in edits:
                by_par.setdefault(f.par, []).append((f.start, f.end, new))
        for i, items in by_par.items():
            for start, end, new in sorted(items, reverse=True):
                self._replace_span(i, start, end, new)
                done += 1
        for i, new in edits.items():
            self._set_text(i, new)
            done += 1
        for old, new in replaces:
            if not old or new is None or old == new or not str(new).strip():
                continue
            for i in range(len(self.pars)):
                text = self.text(i)
                if old not in text:
                    continue
                pos = [m.start() for m in re.finditer(re.escape(old), text)]
                for a in reversed(pos):
                    self._replace_span(i, a, a + len(old), new)
                    done += 1
        return done

    def save(self, out_path, values=None, replaces=None, edits=None):
        n = self.apply(values, replaces, edits)
        self.doc.save(out_path)
        return n


def selftest():
    """Проверка в собранной программе: документ создаётся, поля находятся, значения подставляются."""
    import os
    import tempfile
    try:
        import docx
        tmp = tempfile.mkdtemp(prefix="stampstudio_wt_")
        a, b = os.path.join(tmp, "a.docx"), os.path.join(tmp, "b.docx")
        d = docx.Document()
        d.add_paragraph("Договор № БМ-000 от «__» ________ 2026 г., сумма 00,00 ( ______ ) руб., ФИО ________")
        d.save(a)
        w = WordDoc(a)
        kinds = [f.kind for f in w.fields]
        w.save(b, {0: "11.11.2026", 1: "1992000", 2: "Ефименко А. И."}, [("БМ-000", "БМ-619")])
        text = WordDoc(b).text(0)
        ok = (kinds == ["date", "sum", "blank"] and "«11» ноября 2026 г." in text and "БМ-619" in text
              and "1 992 000,00 (Один миллион девятьсот девяносто две тысячи)" in text and "Ефименко А. И." in text)
        for f in (a, b):
            os.remove(f)
        os.rmdir(tmp)
        return "ok" if ok else "bad"
    except Exception as e:
        return "fail:" + str(e)[:80]


# ----------------------------------------------------------------------------- данные клиента
KEYS = (("fio", "ФИО клиента"), ("fio_short", "Фамилия И. О."), ("passport", "Паспорт: серия и номер"),
        ("passport_issued", "Паспорт: кем и когда выдан"), ("address", "Адрес регистрации"),
        ("birth", "Дата рождения"), ("phone", "Телефон"), ("email", "E-mail"), ("city", "Город"),
        ("contract_no", "Номер договора"), ("contract_date", "Дата договора"),
        ("car", "Марка и модель"), ("year", "Год выпуска"), ("mileage", "Пробег, тыс. км"),
        ("engine_volume", "Объём двигателя"), ("engine_type", "Тип двигателя"), ("gearbox", "Тип КПП"),
        ("body", "Тип кузова"), ("color", "Цвет кузова"), ("interior", "Салон"), ("vin", "VIN"),
        ("weight", "Вес, кг"), ("delivery_address", "Адрес доставки"),
        ("sum_delivery", "Стоимость доставки"), ("sum_customs", "Таможенное оформление"),
        ("sum_car", "Стоимость автомобиля"), ("sum_fee", "Вознаграждение исполнителя"),
        ("sum_total", "Общая стоимость"), ("sum_invoice", "Стоимость по инвойсу"),
        ("doc_no", "Номер этого документа"))
KEY_TITLES = dict(KEYS)
KEY_TITLES["engine_combo"] = "Объём / тип двигателя"
CARD_GROUPS = (("Клиент", ("fio", "passport", "passport_issued", "address", "birth", "phone", "email", "city")),
               ("Договор", ("contract_no", "contract_date")),
               ("Автомобиль", ("car", "year", "mileage", "engine_volume", "engine_type", "gearbox", "body", "color",
                               "interior", "vin", "weight")),
               ("Доставка и деньги", ("delivery_address", "sum_delivery", "sum_customs", "sum_car", "sum_fee",
                                      "sum_total", "sum_invoice")))
CARD_KEYS = tuple(k for _g, ks in CARD_GROUPS for k in ks)
DUMMY_KEYS = {"ФИО": "fio", "ФИО коротко": "fio_short", "Паспорт": "passport", "Телефон": "phone",
              "Номер договора": "contract_no"}
_GUESS = ((r"vin\W*$", "vin"), (r"марка и модель\W*$|марка, модель\W*$", "car"), (r"год выпуска\W*$", "year"),
          (r"e-?mail\W*$", "email"), (r"тел\.?\W*$|телефон\W*$", "phone"), (r"рожден\w*\W*$", "birth"),
          (r"выдан\w*\W*$", "passport_issued"), (r"(?<![а-яё])паспорт\s*(?:№|серия)?\W*$", "passport"),
          (r"адрес доставки\W*$", "delivery_address"),
          (r"адрес\w*\W*$|адрес регистрации\W*$", "address"),
          (r"гражданин(?:\(ка\))?\W*$|фио\W*$|заказчик \(декларант\)\W*$", "fio"))
# подписи строк в таблицах («№ | название | значение») — ищутся в любом месте названия
_GUESS_LABEL = ((r"заказчик \(декларант\)", "fio"), (r"^заказчик$", "fio_short"),
                (r"марка и модель|марка, модель", "car"), (r"год выпуска", "year"), (r"пробег", "mileage"),
                (r"объ[её]м двигателя.*тип двигателя", "engine_combo"), (r"объ[её]м двигателя", "engine_volume"),
                (r"тип двигателя", "engine_type"), (r"тип кпп|коробк", "gearbox"), (r"тип кузова", "body"),
                (r"цвет кузова", "color"), (r"салон", "interior"), (r"\bvin\b", "vin"), (r"\bвес\b", "weight"),
                (r"адрес доставки", "delivery_address"), (r"стоимость доставки", "sum_delivery"),
                (r"таможенное оформление", "sum_customs"), (r"стоимость автомобиля", "sum_car"),
                (r"вознаграждение", "sum_fee"), (r"общая стоимость", "sum_total"),
                (r"стоимость по инвойсу", "sum_invoice"), (r"e-?mail", "email"), (r"^(?:моб\.?\s*)?телефон|^тел\b", "phone"),
                (r"дата рождения", "birth"), (r"^выдан", "passport_issued"), (r"^паспорт", "passport"),
                (r"адрес регистрации", "address"), (r"^фио", "fio"))
TOTAL_RE = re.compile(r"\bитого\b|общая стоимость", re.I)


def guess_label(label):
    """По названию строки таблицы («Марка и модель автомобиля») понять, что это за значение."""
    s = re.sub(r"[\s_]+", " ", re.sub(r"^\d+\.?\s+", "", str(label or "").lower())).strip(" :")
    for pat, key in _GUESS_LABEL:
        if re.search(pat, s):
            return key
    return ""


def guess_key(before):
    """По словам перед пустым местом понять, что туда вписывается («паспорт ___» → passport)."""
    s = re.sub(r"[\s_]+", " ", str(before or "").lower()).strip()
    for pat, key in _GUESS:
        if re.search(pat, s):
            return key
    return ""


# ----------------------------------------------------------------------------- нумерация документов
def next_number(last, year=None, reset_year=True):
    """Следующий номер в том же виде: «БМ-619» → «БМ-620», «329–2026» → «330–2026».
    Если в номере стоит год и он сменился — год обновляется, а счёт начинается с 1."""
    last = str(last or "").strip()
    groups = list(re.finditer(r"\d+", last))
    if not groups:
        return ""
    year_g = next((g for g in groups if len(g.group()) == 4 and g.group().startswith("20")), None) if len(groups) > 1 else None
    num_g = next((g for g in groups if g is not year_g), None)
    if num_g is None:
        return ""
    n = int(num_g.group()) + 1
    new_year = year_g.group() if year_g else ""
    if year_g is not None and year and str(year) != year_g.group():
        new_year = str(year)
        if reset_year:
            n = 1
    out = list(last)
    spans = [(num_g.start(), num_g.end(), str(n).zfill(len(num_g.group())))]
    if year_g is not None:
        spans.append((year_g.start(), year_g.end(), new_year))
    for a, b, text in sorted(spans, reverse=True):
        out[a:b] = list(text)
    return "".join(out)


def number_value(text):
    """Число-счётчик внутри номера (для сравнения «какой больше»)."""
    groups = re.findall(r"\d+", str(text or ""))
    if not groups:
        return -1
    rest = [g for g in groups if not (len(g) == 4 and g.startswith("20"))] if len(groups) > 1 else groups
    return int((rest or groups)[0])


# ----------------------------------------------------------------------------- карточка клиента в папке
CARD_FILE = "Карточка клиента.ssclient"
ON_CARD_SAVED = None            # программа подставляет сюда свою функцию: fn(папка)
CARD_FALLBACK = None            # fn(папка) → данные клиента из облака, если в папке карточки ещё нет


def card_path(folder):
    import os
    return os.path.join(folder, CARD_FILE)


def card_load(folder, fallback=True):
    """Карточка клиента из папки: {ключ: значение}. Пусто, если карточки нет.
    Если в папке карточки ещё нет, а в облаке есть клиент с таким же названием папки — берётся он."""
    import json
    import os
    try:
        with open(card_path(folder), "r", encoding="utf-8") as f:
            data = json.load(f)
        vals = data.get("values") if isinstance(data, dict) else None
        return {k: str(v) for k, v in (vals or {}).items() if str(v).strip()}
    except (OSError, ValueError):
        pass
    if fallback and CARD_FALLBACK is not None:
        try:
            return {k: str(v) for k, v in (CARD_FALLBACK(folder) or {}).items() if str(v).strip()}
        except Exception:
            pass
    return {}


def card_save(folder, values):
    """Записать карточку в папку клиента (файл помечается скрытым). True — получилось."""
    import datetime
    import json
    import os
    import sys
    path = card_path(folder)
    vals = {k: str(v).strip() for k, v in (values or {}).items() if str(v).strip()}
    try:
        if not vals:
            if os.path.exists(path):
                _unhide(path)
                os.remove(path)
            if ON_CARD_SAVED is not None:
                ON_CARD_SAVED(folder)
            return True
        _unhide(path)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"app": "Stamp Studio", "saved": datetime.datetime.now().isoformat(timespec="seconds"),
                       "values": vals}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(path, 0x02)      # скрытый
            except Exception:
                pass
        if ON_CARD_SAVED is not None:
            try:
                ON_CARD_SAVED(folder)
            except Exception:
                pass
        return True
    except OSError:
        return False


def _unhide(path):
    import os
    import sys
    if sys.platform == "win32" and os.path.exists(path):
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(path, 0x80)          # обычный: скрытый файл не перезаписать
        except Exception:
            pass


def derive(values):
    """Дописать производные значения: «Фамилия И. О.», «объём / тип двигателя»."""
    out = dict(values or {})
    if out.get("fio") and not out.get("fio_short"):
        out["fio_short"] = initials(out["fio"])
    vol, typ = out.get("engine_volume", ""), out.get("engine_type", "")
    if (vol or typ) and not out.get("engine_combo"):
        out["engine_combo"] = " / ".join(x for x in (vol, typ) if x)
    return out


# ----------------------------------------------------------------------------- данные из распознанного текста
_BRANDS = ("Mercedes-Benz|Mercedes|BMW|Audi|Volkswagen|VW|Skoda|Škoda|Toyota|Lexus|Dacia|Renault|Peugeot|Citroen|"
           "Citroën|Volvo|Kia|Hyundai|Ford|Opel|Mazda|Nissan|Porsche|Land Rover|Range Rover|Jeep|Tesla|Honda|"
           "Mitsubishi|Subaru|Seat|Cupra|Fiat|Mini|Suzuki|Jaguar|Infiniti|Chevrolet|Alfa Romeo|Genesis|BYD|Geely")


def parse_client_text(text):
    """Достать из распознанного текста то, что узнаётся по правилам: паспорт, ФИО, даты, VIN, автомобиль.
    Возвращает {ключ: значение} — только то, в чём есть уверенность; остальное человек впишет сам."""
    t = str(text or "")
    flat = re.sub(r"[ \t ]+", " ", t)
    one = re.sub(r"\s+", " ", flat)
    out = {}
    m = re.search(r"(?<![A-Z0-9])(?=[A-HJ-NPR-Z0-9]*\d)(?=[A-HJ-NPR-Z0-9]*[A-HJ-NPR-Z])([A-HJ-NPR-Z0-9]{17})(?![A-Z0-9])",
                  one.upper())
    if m:
        out["vin"] = m.group(1)
    m = re.search(r"(?<!\d)(\d{2})\s?(\d{2})\s?(?:№\s?)?(\d{6})(?!\d)", one)
    if m and re.search(r"паспорт|фамилия|выдан|рожден", one.lower()):
        out["passport"] = f"{m.group(1)} {m.group(2)} {m.group(3)}"
    else:
        m = re.search(r"\b([A-Z]{2}\d{7})\b", one)
        if m and re.search(r"паспорт|пашпарт|passport", one.lower()):
            out["passport"] = m.group(1)
    dates = [(x.start(), x.group(1)) for x in re.finditer(r"(?<!\d)(\d{2}[.\s]\d{2}[.\s](?:19|20)\d{2})(?!\d)", one)]
    norm = lambda d: re.sub(r"\s", ".", d)

    def near(word):
        k = one.lower().find(word)
        if k < 0 or not dates:
            return ""
        after = [d for p, d in dates if 0 <= p - k <= 90]
        return norm(after[0]) if after else ""

    b = near("рожден")
    if b:
        out["birth"] = b
    issued_date = near("дата выдачи") or near("выдач")
    low = one.lower()
    k = low.find("выдан")
    if k >= 0:
        seg = one[k + 5:k + 220]
        seg = re.split(r"дата выдачи|код подразделения|личный код|фамилия", seg, flags=re.I)[0]
        seg = re.sub(r"(?<!\d)\d{2}[.\s]\d{2}[.\s](?:19|20)\d{2}(?!\d)", " ", seg)
        seg = re.sub(r"\s+", " ", seg).strip(" :,.-")
        if re.search(r"мвд|уфмс|овд|увд|отдел|гу |ровд|рувд", seg.lower()) and len(seg) >= 8:
            out["passport_issued"] = (seg + (" " + issued_date if issued_date else "")).strip()
    if "passport_issued" not in out and issued_date:
        out["passport_issued"] = issued_date
    parts = []
    for lab in ("Фамилия", "Имя", "Отчество"):
        m = re.search(lab + r"\W{0,4}([А-ЯЁ][А-ЯЁа-яё-]{1,30})", flat)
        if m:
            parts.append(m.group(1).capitalize() if m.group(1).isupper() else m.group(1))
    if len(parts) == 3:
        out["fio"] = " ".join(parts)
    else:
        m = re.search(r"\b([А-ЯЁ][а-яё-]{1,30})\s+([А-ЯЁ][а-яё]{1,20})\s+([А-ЯЁ][а-яё]{2,20}(?:вич|вна|ична|ьич|оглы|кызы))\b", one)
        if m:
            out["fio"] = " ".join(m.groups())
        else:
            m = re.search(r"\b([А-ЯЁ-]{2,30})\s+([А-ЯЁ]{2,20})\s+([А-ЯЁ]{3,20}(?:ВИЧ|ВНА|ИЧНА|ЬИЧ))\b", one)
            if m:
                out["fio"] = " ".join(x.capitalize() for x in m.groups())
    m = re.search(r"(?:зарегистрирован\w*(?: по адресу)?|адрес регистрации|место жительства)\W{0,6}(.{12,140}?)(?:\s{2,}|$|, именуем|\. [А-ЯЁ])", one, re.I)
    if m and re.search(r"ул\.|улица|пр-т|д\.|дом |кв\.|г\. ?[А-ЯЁ]", m.group(1)):
        out["address"] = m.group(1).strip(" ,.;")
    m = re.search(r"\b(" + _BRANDS + r")\b[ \t]+([A-Za-zА-Яа-яЁё0-9][\w.-]*(?:[ \t]+[A-Za-z0-9][\w.-]*){0,2})", flat)
    if m:
        out["car"] = (m.group(1) + " " + m.group(2)).strip()
    m = re.search(r"(?:год выпуска|год изготовления|Herstellungsjahr\w*|Baujahr)\D{0,25}((?:19|20)\d{2})", one, re.I)
    if m:
        out["year"] = m.group(1)
    m = re.search(r"(?<!\d)(\d{3,4})\s?(?:см3|см³|куб\.? ?см|cm3|cm³|ccm)", one, re.I)
    if m:
        out["engine_volume"] = m.group(1) + " см³"
    m = re.search(r"(?:масса|вес)[^\d]{0,40}?(\d{3,4})\s?кг", one, re.I)
    if m:
        out["weight"] = m.group(1)
    m = re.search(r"(\+?\d[\d() -]{9,16}\d)", one)
    if m and re.search(r"тел|моб|phone", one.lower()):
        out["phone"] = m.group(1).strip()
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", one)
    if m:
        out["email"] = m.group(0)
    return out
