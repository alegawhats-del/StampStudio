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
                if idx >= 1 and 2 <= n <= 4 and idx == n - 1 and 2 <= len(ctx) <= 110 and not re.search(r"[_/]", ctx):
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
        out.sort(key=lambda f: (f.par, f.start))
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
