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

HL, SHD, VAL = f"{{{W}}}highlight", f"{{{W}}}shd", f"{{{W}}}val"


def _yellowish(fill):
    """Заливка текста жёлтого тона (её тоже используют как выделение)."""
    m = re.fullmatch(r"([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})", str(fill or ""))
    if not m:
        return False
    r, g, b = (int(x, 16) for x in m.groups())
    return r >= 200 and g >= 190 and b <= 170


def money_cell(value):
    """«22416,66» → «22 416,66 (Двадцать две тысячи четыреста шестнадцать) руб. 66 коп.»; не число — как есть."""
    n = parse_number(value)
    if not n:
        return str(value or "").strip()
    return f"{format_number(n[0])},{n[1]:02d} ({number_words(n[0])}) руб. {n[1]:02d} коп."


def date_words(value):
    """«17.11.2026» → «17 ноября 2026»; None, если это не дата."""
    d = parse_date(value)
    return f"{d[0]:02d} {MONTHS[d[1] - 1]} {d[2]}" if d else None


def money_words(whole, sample=""):
    """Сумма прописью по образцу: «Девятьсот шесть тысяч пятьсот рублей 00 копеек» → те же слова для другой суммы."""
    words = number_words(int(whole), capital=not sample or sample[:1].isupper())
    m = re.search(r"\s(?:(российск|белорусск)\w*\s+)?рубл\w*(.*)$", sample)
    if not m:
        return words
    adj = {"российск": ("российский", "российских", "российских"), "белорусск": ("белорусский", "белорусских", "белорусских")}
    out = words + " "
    if m.group(1):
        out += _plural(int(whole), adj[m.group(1).lower()]) + " "
    return out + _plural(int(whole), ("рубль", "рубля", "рублей")) + m.group(2)


# ----------------------------------------------------------------------------- русский → латиница / немецкий
_ICAO = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                 ("a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
                  "f", "kh", "ts", "ch", "sh", "shch", "ie", "y", "", "e", "iu", "ia")))
_DE = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ("a", "b", "w", "g", "d", "e", "jo", "sch", "s", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
                "f", "ch", "z", "tsch", "sch", "schtsch", "", "y", "", "e", "ju", "ja")))


def has_cyrillic(text):
    return bool(re.search(r"[А-Яа-яЁё]", str(text or "")))


def _translit(text, table, de=False):
    out = []
    s = str(text or "")
    for i, ch in enumerate(s):
        low = ch.lower()
        if low not in table:
            out.append(ch)
            continue
        t = table[low]
        if de:
            prev = s[i - 1].lower() if i else ""
            nxt = s[i + 1].lower() if i + 1 < len(s) else ""
            if low == "е" and (not prev.isalpha() or prev in "аеёиоуыэюяъь"):
                t = "je"
            elif low == "с" and prev in "аеёиоуыэюя" and nxt in "аеёиоуыэюя" and prev and nxt:
                t = "ss"
            elif low == "й" and prev in "иы":
                t = ""                                       # -ий, -ый → -i, -y
        if ch.isupper():
            t = t[:1].upper() + t[1:] if not (i + 1 < len(s) and s[i + 1].isupper()) else t.upper()
        out.append(t)
    return "".join(out)


def translit_name(text):
    """ФИО латиницей, как в загранпаспорте: «Воробьев Владимир Николаевич» → «Vorobev Vladimir Nikolaevich»."""
    return _translit(text, _ICAO)


def translit_de(text):
    """Русское слово в немецкой записи: «Чайковский» → «Tschaikowski», «Воронеж» → «Woronesch»."""
    return _translit(text, _DE, de=True)


_ADDR_WORDS = (
    (r"(?:область|обл\.?)", "Region"), (r"(?:район|р-н)", "Bezirk"), (r"(?:республика|респ\.?)", "Republik"),
    (r"(?:край)", "Region"), (r"(?:город|г\.?)", "Stadt"), (r"(?:посёлок|поселок|пгт\.?|пос\.?|п\.)", "Siedlung"),
    (r"(?:село|деревня|дер\.?|с\.)", "Dorf"), (r"(?:улица|ул\.?)", "Straße"), (r"(?:проспект|просп\.?|пр-т)", "Prospekt"),
    (r"(?:переулок|пер\.?)", "Gasse"), (r"(?:проезд|пр-д)", "Durchfahrt"), (r"(?:шоссе|ш\.)", "Chaussee"),
    (r"(?:бульвар|б-р)", "Boulevard"), (r"(?:площадь|пл\.?)", "Platz"), (r"(?:микрорайон|мкр\.?)", "Mikrobezirk"),
    (r"(?:дом|д\.)", "Haus"), (r"(?:корпус|корп\.?|к\.)", "Gebäude"), (r"(?:строение|стр\.?)", "Bau"),
    (r"(?:квартира|кв\.?)", "Wohnung"), (r"(?:комната|ком\.?)", "Zimmer"))
_COUNTRIES = {"россия": "Russland", "рф": "Russland", "российская федерация": "Russland", "беларусь": "Belarus",
              "республика беларусь": "Belarus", "казахстан": "Kasachstan", "германия": "Deutschland"}


_REGIONS = {k + "ая": v for k, v in (
    ("московск", "Moskau"), ("ленинградск", "Leningrad"), ("воронежск", "Woronesch"), ("смоленск", "Smolensk"),
    ("брянск", "Brjansk"), ("курск", "Kursk"), ("белгородск", "Belgorod"), ("орловск", "Orjol"), ("тульск", "Tula"),
    ("калужск", "Kaluga"), ("тверск", "Twer"), ("псковск", "Pskow"), ("новгородск", "Nowgorod"), ("рязанск", "Rjasan"),
    ("владимирск", "Wladimir"), ("ивановск", "Iwanowo"), ("ярославск", "Jaroslawl"), ("костромск", "Kostroma"),
    ("липецк", "Lipezk"), ("тамбовск", "Tambow"), ("ростовск", "Rostow"), ("волгоградск", "Wolgograd"),
    ("саратовск", "Saratow"), ("самарск", "Samara"), ("пензенск", "Pensa"), ("ульяновск", "Uljanowsk"),
    ("нижегородск", "Nischni Nowgorod"), ("кировск", "Kirow"), ("оренбургск", "Orenburg"), ("челябинск", "Tscheljabinsk"),
    ("свердловск", "Swerdlowsk"), ("тюменск", "Tjumen"), ("омск", "Omsk"), ("новосибирск", "Nowosibirsk"),
    ("томск", "Tomsk"), ("кемеровск", "Kemerowo"), ("иркутск", "Irkutsk"), ("астраханск", "Astrachan"),
    ("калининградск", "Kaliningrad"), ("мурманск", "Murmansk"), ("архангельск", "Archangelsk"), ("вологодск", "Wologda"),
    ("курганск", "Kurgan"), ("амурск", "Amur"), ("сахалинск", "Sachalin"), ("минск", "Minsk"), ("брестск", "Brest"),
    ("гродненск", "Grodno"), ("гомельск", "Gomel"), ("витебск", "Witebsk"), ("могилёвск", "Mogiljow"), ("могилевск", "Mogiljow"))}
_REGIONS.update({"краснодарский": "Krasnodar", "ставропольский": "Stawropol", "красноярский": "Krasnojarsk", "пермский": "Perm",
                 "алтайский": "Altai", "приморский": "Primorje", "хабаровский": "Chabarowsk"})
_CITIES = {"москва": "Moskau", "санкт-петербург": "Sankt Petersburg", "минск": "Minsk", "нижний новгород": "Nischni Nowgorod",
           "ростов-на-дону": "Rostow am Don"}


def _nominative(word):
    """«Чайковского» → «Чайковский» (если есть словарь); иначе как было."""
    try:
        import stamp_decline as D
        m = D._analyzer()
        if m is None:
            return word
        ps = m.parse(word)[:6]
        for p_ in ps:                                        # «Гагарина», «Чайковского» — улица имени человека
            if "Surn" in p_.tag and "masc" in p_.tag and "gent" in p_.tag and "sing" in p_.tag:
                f = p_.inflect({"nomn"})
                if f is not None:
                    return f.word[:1].upper() + f.word[1:] if word[:1].isupper() else f.word
        if any("nomn" in p_.tag for p_ in ps):
            return word                                      # «Заводской», «Советская» — уже в начальной форме
        for p_ in ps:
            if "Surn" in p_.tag or p_.tag.POS == "ADJF":
                f = p_.inflect({"nomn"}) if "plur" not in p_.tag else None
                if f is not None:
                    return f.word[:1].upper() + f.word[1:] if word[:1].isupper() else f.word
        return word
    except Exception:
        return word


def address_de(text):
    """Российский адрес по-немецки: «обл. Воронежская, г. Бутурлиновка, ул. Чайковского, д. 11» →
    «Region Woronesch, Stadt Buturlinowka, Tschaikowski-Straße, Haus 11». Набросок: проверьте глазами."""
    parts = []
    for part in [x.strip() for x in str(text or "").split(",") if x.strip()]:
        low = part.lower()
        if low in _COUNTRIES:
            parts.append(_COUNTRIES[low])
            continue
        if re.fullmatch(r"\d{6}", part) or not has_cyrillic(part):
            parts.append(part)
            continue
        kind, rest = "", part
        for pat, de in _ADDR_WORDS:
            m = re.match(rf"^{pat}\s*(?=[А-ЯЁа-яё\d«\"])(.+)$", part, re.I) or re.match(rf"^(.+?)\s+{pat}$", part, re.I)
            if m and (m.group(1)[:1].isupper() or m.group(1)[:1].isdigit()):
                kind, rest = de, m.group(1).strip()
                if kind == "Haus" and not rest[:1].isdigit():
                    kind = "Dorf"                            # «д. Ивановка» — деревня, «д. 11» — дом
                break
        if rest.lower() in _CITIES and kind in ("Stadt", ""):
            parts.append(("Stadt " if kind else "") + _CITIES[rest.lower()])
        elif kind in ("Haus", "Wohnung", "Gebäude", "Bau", "Zimmer"):
            parts.append(f"{kind} {translit_de(rest)}")
        elif kind in ("Straße", "Gasse", "Prospekt", "Platz", "Boulevard", "Chaussee", "Durchfahrt"):
            num = re.match(r"^(.*?)[\s]+(\d[\w/-]*)$", rest)
            if num:
                rest = num.group(1)
            words = [_nominative(w) for w in rest.split()]
            parts.append("-".join(translit_de(w) for w in words) + "-" + kind + (" " + num.group(2) if num else ""))
        elif kind in ("Region", "Republik"):
            parts.append(f"{kind} {_REGIONS.get(rest.lower()) or translit_de(rest)}")
        elif kind:
            parts.append(f"{kind} {translit_de(rest)}")
        else:
            parts.append(translit_de(part))
    return ", ".join(parts)


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
RE_SUM_UNIT = re.compile(r"\s*(?:(?:российск\w*|белорусск\w*)\s+)?руб\w*\.?(?:\s*\d{2}\s*коп\w*\.?)?\s*", re.I)
RE_BLANK = re.compile(r"_{3,}")
RE_CITY = re.compile(r"пригон\w*\s+транспортного\s+средства\s+в\s+г\.\s*([А-ЯЁ][А-ЯЁа-яё\- ]{1,40}?),\s*Российск")
# дата, уже вписанная в готовый документ: «20» ноября 2026 года — чтобы её можно было поменять
RE_DATE_SET = re.compile(r"«\s*(\d{1,2})\s*»\s*(" + "|".join(MONTHS) + r")\s*(\d{4})(?:\s*(г\.|года|год))?")
RE_DATE_LINE = re.compile(r"^(г\.\s*\S.*?\S)(\s{8,})(«[^»]{1,4}»\s+\S+\s+\d{4}\s+года)(\s*)$")
LINE_BREAK = " "                                  # перенос строки внутри абзаца (в файле — <w:br/>)
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
                return value                   # «Бесплатно», «Включено в стоимость» — словом, без «руб. 00 коп.»
            whole, frac = num
            words = number_words(whole, capital=self.meta.get("capital", True))
            dec = f",{frac:02d}" if self.meta.get("decimals") else ""
            unit = self.meta.get("unit", "")
            if frac:                                   # «руб. 66 коп.» — копейки в хвосте те же, что в сумме
                unit = re.sub(r"\b00(\s*коп)", f"{frac:02d}\\1", unit)
            return f"{format_number(whole, self.meta.get('sep', ' '))}{dec} ({words})" + unit
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
        self.highlights = self._find_highlights()

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
                    elif first is p and not whole and re.fullmatch(r"№\s*Наименование", ctx.strip()):
                        # шапка таблицы приложения «№ | Наименование | …» — в третьей ячейке стоит номер договора
                        out.append(Field("cell", i, 0, 0, "Номер договора — в шапке таблицы",
                                         meta={"key": "contract_no", "twin": True}))
                continue
            taken = []
            for m in RE_DATE.finditer(text):
                out.append(Field("date", i, m.start(), m.end(), self._snip(text, m.start(), m.end(), "date"),
                                 meta={"tail": m.group(2) or ""}))
                taken.append(m.span())
            for m in RE_DATE_SET.finditer(text):
                cur = f"{int(m.group(1)):02d}.{MONTHS.index(m.group(2)) + 1:02d}.{m.group(3)}"
                out.append(Field("date", i, m.start(), m.end(), self._snip(text, m.start(), m.end(), "date"),
                                 current=cur, meta={"tail": m.group(4) or "", "set": True}))
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
                end, unit = m.end(), ""
                um = RE_SUM_UNIT.fullmatch(text[m.end():])
                if ctx and um and not text[:m.start()].strip():
                    end, unit = len(text), text[m.end():].rstrip()   # ячейка «сумма руб. 00 коп.» — единицы часть поля
                out.append(Field("sum", i, m.start(), end, label,
                                 current="" if zero else format_number(int(digits)) + (m.group(2) or ""),
                                 meta={"decimals": bool(m.group(2)), "capital": blank or words.strip()[:1].isupper(),
                                       "sep": " " if " " in m.group(1) else " ", "unit": unit}))
                taken.append((m.start(), end))
            m = RE_CITY.search(text)
            if m:
                out.append(Field("cell", i, m.start(1), m.end(1), "Город пригона (в тексте договора)",
                                 current=m.group(1), meta={"key": "city"}))
                taken.append(m.span(1))
            ctx, idx, n, cell_pars = self._cell_ctx(p)
            for m in RE_BLANK.finditer(text):
                if any(a <= m.start() < b for a, b in taken):
                    continue
                before, after = text[:m.start()].rstrip(), text[m.end():].lstrip()
                if (before.endswith("/") and (after.startswith("/") or not after)) or (not before and after.startswith("/")):
                    continue                           # «/ ________ /» — место для подписи
                if not before and not after and cell_pars:
                    k = cell_pars.index(p)
                    rest_txt = "".join("".join(t.text or "" for t in x.iter(T)) for x in cell_pars[k + 1:]).strip()
                    if k >= 2 and not rest_txt and len(cell_pars) >= 4:
                        continue                       # линия под реквизитами стороны — место для подписи
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

    # ---- жёлтое выделение: так в шаблоне помечают то, что меняется от документа к документу
    @staticmethod
    def _marked(t):
        r = t.getparent()
        while r is not None and r.tag != R:
            r = r.getparent()
        rpr = r.find(RPR) if r is not None else None
        if rpr is None:
            return ""
        hl = rpr.find(HL)
        if hl is not None and (hl.get(VAL) or "").lower() not in ("", "none", "white", "black"):
            return "yellow" if "yellow" in hl.get(VAL).lower() else "fixed"   # зелёным и др. — постоянные реквизиты
        shd = rpr.find(SHD)
        return "yellow" if shd is not None and _yellowish(shd.get(f"{{{W}}}fill")) else ""

    def _find_highlights(self):
        """[{par, start, end, text, label, ctx, before}] — выделенные цветом куски, по порядку."""
        out = []
        for i, ts in enumerate(self._texts):
            if not ts or not any(self._marked(t) for t in ts):
                continue
            text, pos, spans = self.text(i), 0, []
            for t in ts:
                n = len(t.text or "")
                col = self._marked(t) if n else ""
                if col:
                    if spans and spans[-1][1] == pos and spans[-1][2] == col:
                        spans[-1][1] = pos + n
                    else:
                        spans.append([pos, pos + n, col])
                pos += n
            ctx = self._cell_ctx(self.pars[i])[0]
            near = ""                                  # подпись — ближайшая слева ячейка с текстом
            tc = self.pars[i].getparent()
            while tc is not None and tc.tag != TC:
                tc = tc.getparent()
            if tc is not None:
                for c in reversed([c for c in tc.getparent() if c.tag == TC][:[c for c in tc.getparent() if c.tag == TC].index(tc)]):
                    near = re.sub(r"\s+", " ", "".join(t.text or "" for t in c.iter(T))).strip()
                    if re.search(r"[A-Za-zА-Яа-яЁё]{2,}", near):
                        break
                    near = ""
            for a, b, col in spans:
                while a < b and text[a] in " \t\u00a0\n":
                    a += 1
                while b > a and text[b - 1] in " \t\u00a0\n":
                    b -= 1
                if b <= a:
                    continue
                before = re.sub(r"\s+", " ", text[:a][-60:]).strip()
                label = before if len(before) >= 3 else re.sub(r"^\d+\.?\s+", "", near)
                label = re.sub(r"[\s:(«\"№]+$", "", label)[-46:].strip()
                out.append({"par": i, "start": a, "end": b, "text": text[a:b], "label": label,
                            "ctx": ctx, "before": text[:a][-70:], "fixed": col == "fixed"})
        return out

    def strip_highlights(self):
        """Готовому документу выделение не нужно: убрать цветной фон у всего текста."""
        n = 0
        for el in list(self.doc.element.body.iter(HL)):
            if (el.get(VAL) or "").lower() not in ("", "none"):
                el.getparent().remove(el)
                n += 1
        for el in list(self.doc.element.body.iter(SHD)):
            if el.getparent().tag == RPR and _yellowish(el.get(f"{{{W}}}fill")):
                el.getparent().remove(el)
                n += 1
        for _title, zone, _ids in self.zones:
            for el in list(zone.iter(HL)):
                el.getparent().remove(el)
                n += 1
        return n

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
        if LINE_BREAK in new or re.fullmatch(r"\s*\+?\d[\d() \-]{6,}\d\s*", new):   # переносы придут из нового текста (или остался один номер) — прежние убираем
            for br in [x for x in self.pars[i].iter(f"{{{W}}}br") if not x.get(f"{{{W}}}type")]:
                br.getparent().remove(br)
        a = 0
        while a < min(len(old), len(new)) and old[a] == new[a]:
            a += 1
        b = 0
        while b < min(len(old), len(new)) - a and old[len(old) - 1 - b] == new[len(new) - 1 - b]:
            b += 1
        mid_old, mid_new = old[a:len(old) - b], new[a:len(new) - b]
        if len(self._texts[i]) < 2 or not mid_old or len(mid_old) * len(mid_new) > 4_000_000:
            self._replace_span(i, a, len(old) - b, mid_new)
            return
        # несколько правок в одном абзаце: каждая попадает в свой кусок, жирное остаётся жирным, обычное — обычным
        import difflib
        ops = difflib.SequenceMatcher(None, mid_old, mid_new, autojunk=False).get_opcodes()
        ops = [(tag, i1, i2, j1, j2) for tag, i1, i2, j1, j2 in ops
               if tag != "equal" or i2 - i1 >= 3 or not mid_old[i1:i2].strip() == ""]
        merged = []                                   # короткие совпадения в пару букв не дробят правку
        for tag, i1, i2, j1, j2 in ops:
            small = tag == "equal" and i2 - i1 < 3
            if merged and (small or merged[-1][0] != "equal") and (tag != "equal" or small):
                m = merged[-1]
                merged[-1] = ("replace", m[1], i2, m[3], j2)
            else:
                merged.append(("replace" if small else tag, i1, i2, j1, j2))
        for tag, i1, i2, j1, j2 in reversed(merged):
            if tag != "equal":
                self._replace_span(i, a + i1, a + i2, mid_new[j1:j2])

    @staticmethod
    def _date_line(old, new):
        mo, mn = RE_DATE_LINE.match(old), RE_DATE_LINE.match(new)
        if not mo or not mn:
            return new
        grow = len(mn.group(3)) - len(mo.group(3))
        gap = mn.group(2)
        if grow > 0:                                   # буква шире пробела примерно вдвое
            gap = gap[:max(6, len(gap) - 2 * grow)]
        return mn.group(1) + gap + mn.group(3).replace(" ", " ")

    # ---- доводка готового документа: то, что нельзя сделать заменой текста
    def finish(self, services=None, total_par=None, align=True, tradein=None):
        if tradein and total_par is not None:              # до доп. услуг: те вставляются выше итога и его не сдвигают
            self._add_tradein_rows(total_par, tradein)
        """services: [(название, текст значения)] — строки доп. услуг перед строкой итога (абзац total_par)."""
        if services and total_par is not None:
            self._add_service_rows(total_par, services)
        self._line_breaks()
        self._phone_gap()
        if align:
            self._align_signatures()

    def _phone_gap(self):
        """Номера телефонов идут сразу под «Моб. телефон:», без пустой строки."""
        txt = lambda x: "".join(t.text or "" for t in x.iter(T)).strip()
        for tc in list(self.doc.element.body.iter(TC)):
            ps = [x for x in tc if x.tag == P]
            for i in range(len(ps) - 2):
                if re.fullmatch(r"(?:моб\.?\s*)?тел\w*\.?:", txt(ps[i]).lower()) and not txt(ps[i + 1]) \
                        and re.match(r"\+?\d[\d() \-]{6,}", txt(ps[i + 2])):
                    tc.remove(ps[i + 1])
                    break

    def _line_breaks(self):
        for t in list(self.doc.element.body.iter(T)):
            if t.text and LINE_BREAK in t.text:
                parts = t.text.split(LINE_BREAK)
                t.text = parts[0]
                at = t
                for part in parts[1:]:
                    br = t.makeelement(f"{{{W}}}br", {})
                    at.addnext(br)
                    nt = t.makeelement(T, {f"{{{XML}}}space": "preserve"})
                    nt.text = part
                    br.addnext(nt)
                    at = nt

    @staticmethod
    def _cell_set(tc, text):
        """Текст ячейки одной строкой, с оформлением её первого куска."""
        ps = [x for x in tc if x.tag == P]
        for extra in ps[1:]:
            tc.remove(extra)
        lines = str(text).split("\n")
        text = lines[0]
        ts = [t for t in ps[0].iter(T)] if ps else []
        if ts:
            ts[0].text = text
            ts[0].set(f"{{{XML}}}space", "preserve")
            for t in ts[1:]:
                t.text = ""
        elif ps:
            r = ps[0].makeelement(R, {})
            ppr = ps[0].find(PPR)
            if ppr is not None and ppr.find(RPR) is not None:
                r.append(copy.deepcopy(ppr.find(RPR)))
            t = ps[0].makeelement(T, {f"{{{XML}}}space": "preserve"})
            t.text = text
            r.append(t)
            ps[0].append(r)
        at = ps[0] if ps else None
        for line in lines[1:]:                         # вторая строка ячейки — таким же абзацем
            if at is None:
                break
            np_ = copy.deepcopy(ps[0])
            nts = [t for t in np_.iter(T)]
            if nts:
                nts[0].text = line
                for t in nts[1:]:
                    t.text = ""
            at.addnext(np_)
            at = np_

    def _add_service_rows(self, total_par, services):
        p = self.pars[total_par]
        tr = p.getparent()
        while tr is not None and tr.tag != TR:
            tr = tr.getparent()
        if tr is None:
            return 0
        rows = [x for x in tr.getparent() if x.tag == TR]
        k = rows.index(tr)
        if k < 1:
            return 0
        src = rows[k - 1]                              # образец оформления — строка над итогом
        cells_of = lambda row: [c for c in row if c.tag == TC]
        num = lambda row: re.match(r"\s*(\d+)", "".join(t.text or "" for t in cells_of(row)[0].iter(T)))
        base = num(src)
        n0 = int(base.group(1)) if base else k - 1
        dot = "." if base and "." in "".join(t.text or "" for t in cells_of(src)[0].iter(T)) else ""
        for j, (name, value) in enumerate(services, 1):
            new = copy.deepcopy(src)
            cs = cells_of(new)
            if len(cs) < 3:
                return 0
            self._cell_set(cs[0], f"{n0 + j}{dot}")
            self._cell_set(cs[1], name)
            self._cell_set(cs[-1], value)
            tr.addprevious(new)
        if num(tr):
            self._cell_set(cells_of(tr)[0], f"{n0 + len(services) + 1}{dot}")
        return len(services)

    def _add_tradein_rows(self, total_par, items):
        """Под строкой итога: заголовок «Характеристики передаваемого автомобиля» и строки [(название, значение)]."""
        p = self.pars[total_par]
        tr = p.getparent()
        while tr is not None and tr.tag != TR:
            tr = tr.getparent()
        if tr is None:
            return 0
        cells_of = lambda row: [c for c in row if c.tag == TC]
        if len(cells_of(tr)) < 3:
            return 0
        wq = lambda n: f"{{{W}}}{n}"
        head = copy.deepcopy(tr)
        cs = cells_of(head)
        width = 0
        for c in cs:
            tw = c.find(wq("tcPr") + "/" + wq("tcW"))
            try:
                width += int(tw.get(wq("w"))) if tw is not None else 0
            except (TypeError, ValueError):
                pass
        first = cs[-1]                                     # оформление — как у ячейки значения
        for c in cs[:-1]:
            head.remove(c)
        pr = first.find(wq("tcPr"))
        if pr is None:
            pr = first.makeelement(wq("tcPr"), {})
            first.insert(0, pr)
        for old in pr.findall(wq("gridSpan")):
            pr.remove(old)
        tw = pr.find(wq("tcW"))
        if tw is not None and width:
            tw.set(wq("w"), str(width))
        span = pr.makeelement(wq("gridSpan"), {wq("val"): str(len(cs))})
        if tw is not None:
            tw.addnext(span)
        else:
            pr.insert(0, span)
        self._cell_set(first, TRADEIN_TITLE)
        for par in [x for x in first if x.tag == P]:
            ppr = par.find(wq("pPr"))
            if ppr is None:
                ppr = par.makeelement(wq("pPr"), {})
                par.insert(0, ppr)
            for old in ppr.findall(wq("jc")):
                ppr.remove(old)
            jc = ppr.makeelement(wq("jc"), {wq("val"): "center"})
            rpr = ppr.find(wq("rPr"))
            (rpr.addprevious(jc) if rpr is not None else ppr.append(jc))
        dot = "." if "." in "".join(t.text or "" for t in cells_of(tr)[0].iter(T)) else "."
        last = tr
        last.addnext(head)
        last = head
        for j, (name, value) in enumerate(items, 1):
            new = copy.deepcopy(tr)
            c2 = cells_of(new)
            self._cell_set(c2[0], f"{j}{dot}")
            self._cell_set(c2[1], name)
            self._cell_set(c2[-1], value)
            last.addnext(new)
            last = new
        return len(items)

    def _align_signatures(self):
        """Линии для подписей сторон стоят на одной высоте: они переносятся в отдельную строку таблицы."""
        made = 0
        txt_of = lambda x: "".join(t.text or "" for t in x.iter(T)).strip()
        for tbl in list(self.doc.element.body.iter(TBL)):
            for tr in [x for x in tbl if x.tag == TR]:
                cells = [c for c in tr if c.tag == TC]
                if len(cells) != 2:
                    continue
                tails = []
                for c in cells:
                    ps = [x for x in c if x.tag == P]
                    txt = [txt_of(x) for x in ps]
                    last = max((n for n, t_ in enumerate(txt) if t_), default=-1)
                    if last < 2 or not re.fullmatch(r"_{6,}", txt[last]):
                        tails = []
                        break
                    named = bool(RE_INITIALS.search(txt[last - 1])) and len(txt[last - 1]) <= 60
                    tails.append([c, ps, txt, last, named])
                if len(tails) != 2:
                    continue
                both = all(t_[4] for t_ in tails)
                new = copy.deepcopy(tr)
                for el in list(new):
                    if el.tag == TC:
                        for x in [x for x in el if x.tag in (P, TBL)]:
                            el.remove(x)
                    elif el.tag == f"{{{W}}}trPr":
                        for h in el.findall(f"{{{W}}}trHeight"):
                            el.remove(h)
                plan = []
                for c, ps, txt, last, _named in tails:
                    start = last - 1 if both else last      # «Директор Иванов И. И.» остаётся над своей линией
                    gap = 0
                    while start - gap - 1 >= 1 and not txt[start - gap - 1]:
                        gap += 1
                    plan.append((c, ps, start, gap, last))
                keep = min(2, min(g for _c, _ps, _s, g, _l in plan))   # пустые строки над подписью — поровну у обеих сторон
                tail_gap = any(len(ps) > last + 1 for _c, ps, _s, _g, last in plan)    # под линией была пустая строка
                for (c, ps, start, gap, last), nc in zip(plan, [c for c in new if c.tag == TC]):
                    for x in ps[start - gap:start - keep] + ps[last + 1:]:
                        c.remove(x)
                    for x in ps[start - keep:last + 1]:
                        c.remove(x)
                        nc.append(x)
                    if tail_gap:                             # один отступ после линии — у обеих сторон одинаково
                        blank = copy.deepcopy(ps[last])
                        for r_ in [x for x in blank if x.tag != PPR]:
                            blank.remove(r_)
                        nc.append(blank)
                for c in [c for c in tr if c.tag == TC]:
                    self._tc_prop(c, "tcBorders", edge=("bottom", "nil"))      # без черты между текстом и подписью
                for c in [c for c in new if c.tag == TC]:
                    self._tc_prop(c, "tcBorders", edge=("top", "nil"))
                    self._tc_prop(c, "vAlign", val="bottom")                   # линии — на одной высоте, по низу строки
                tr.addnext(new)
                made += 1
        return made

    _TCPR_ORDER = ("tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar", "textDirection",
                   "tcFitText", "vAlign", "hideMark")
    _BORDER_ORDER = ("top", "start", "left", "bottom", "end", "right", "insideH", "insideV", "tl2br", "tr2bl")

    @classmethod
    def _child(cls, parent, name, order):
        q = lambda n: f"{{{W}}}{n}"
        el = parent.find(q(name))
        if el is None:
            el = parent.makeelement(q(name), {})
            later = [parent.find(q(n)) for n in order[order.index(name) + 1:]]
            nxt = next((x for x in later if x is not None), None)
            if nxt is not None:
                nxt.addprevious(el)
            else:
                parent.append(el)
        return el

    @classmethod
    def _tc_prop(cls, tc, name, val=None, edge=None):
        q = lambda n: f"{{{W}}}{n}"
        pr = tc.find(q("tcPr"))
        if pr is None:
            pr = tc.makeelement(q("tcPr"), {})
            tc.insert(0, pr)
        el = cls._child(pr, name, cls._TCPR_ORDER)
        if val is not None:
            el.set(q("val"), val)
        if edge is not None:
            e = cls._child(el, edge[0], cls._BORDER_ORDER)
            for k in list(e.attrib):
                del e.attrib[k]
            e.set(q("val"), edge[1])

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
            self._set_text(i, self._date_line(self.text(i), new))
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

    def save(self, out_path, values=None, replaces=None, edits=None, keep_highlight=False, services=None, total_par=None,
             align=True, tradein=None):
        n = self.apply(values, replaces, edits)
        self.finish(services, total_par, align, tradein)
        if not keep_highlight:
            self.strip_highlights()
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
        ("birth", "Дата рождения"), ("phone", "Телефон"), ("phone2", "Второй телефон"), ("email", "E-mail"), ("city", "Город"),
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
CARD_GROUPS = (("Клиент", ("fio", "passport", "passport_issued", "address", "birth", "phone", "phone2", "email", "city")),
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
                (r"таможенное оформление|таможенные платежи", "sum_customs"), (r"стоимость автомобиля", "sum_car"),
                (r"вознаграждение", "sum_fee"), (r"общая стоимость", "sum_total"),
                (r"стоимость по инвойсу", "sum_invoice"), (r"e-?mail", "email"), (r"^(?:моб\.?\s*)?телефон|^тел\b", "phone"),
                (r"дата рождения", "birth"), (r"^выдан", "passport_issued"), (r"^паспорт", "passport"),
                (r"адрес регистрации", "address"), (r"^фио", "fio"),
                (r"контактное лицо", "contact"), (r"^срок доставки", "delivery_term"))
TOTAL_RE = re.compile(r"\bитого\b|общая стоимость", re.I)


_CITY_GEN = {"москва": "Москвы", "санкт-петербург": "Санкт-Петербурга"}
_CITY_ALIAS = {"мск": "москва", "спб": "санкт-петербург", "питер": "санкт-петербург", "петербург": "санкт-петербург",
               "с-петербург": "санкт-петербург", "санкт петербург": "санкт-петербург"}
RE_FREE_CITY = re.compile(r"\b(?:до|от)\s+г\.\s*(Москв[аыеу]|Санкт-Петербург[ае]?)")


def city_genitive(name):
    """«Москва» → «Москвы», «спб» → «Санкт-Петербурга» — для «до г. …», «от г. …». Незнакомый город — по словарю, иначе как есть."""
    t = " ".join(str(name or "").split())
    low = _CITY_ALIAS.get(t.lower().replace("ё", "е"), t.lower())
    if low in _CITY_GEN:
        return _CITY_GEN[low]
    if not t or not re.fullmatch(r"[А-ЯЁа-яё]+", t):
        return t
    try:
        import stamp_decline as D
        m = D._analyzer()
        for p_ in (m.parse(t)[:4] if m is not None else ()):
            if "NOUN" in p_.tag and "nomn" in p_.tag and "sing" in p_.tag:
                f = p_.inflect({"gent"})
                if f is not None:
                    return f.word[:1].upper() + f.word[1:]
    except Exception:
        pass
    return t


def term_days(text):
    """Срок: «7-10» → «7-10 дней», «3» → «3 дня», «1» → «1 день». Не число — как есть."""
    t = str(text or "").strip()
    m = re.fullmatch(r"(\d+)(?:\s*[-–—]\s*(\d+))?(?:\s*(?:дн\w*|день|дня|дней)\.?)?", t)
    if not m:
        return t
    n = int(m.group(2) or m.group(1))
    word = "дней" if 10 < n % 100 < 20 or n % 10 in (0, 5, 6, 7, 8, 9) else ("день" if n % 10 == 1 else "дня")
    return (f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)) + " " + word


TRADEIN_TITLE = "Характеристики передаваемого автомобиля"
TRADEIN_ROWS = (("model", "Марка и модель автомобиля"), ("year", "Год выпуска"), ("mileage", "Пробег, тыс. км"),
                ("volume", "Объем двигателя (л/см³)"), ("fuel", "Тип двигателя"), ("color", "Цвет кузова"),
                ("owners", "Кол. Владельцев"), ("price", "Оценочная стоимость автомобиля"))


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
    y = re.search(r"(?:19|20)\d{2}", str(out.get("year") or ""))     # для ДКП на немецком: год, объём в см³, пробег числом
    if y:
        out["de_year"], out["de_year2"] = y.group(0), y.group(0)[2:]
    vol = str(out.get("engine_volume") or "")
    cc = re.search(r"(\d[\d \u00a0]{2,6})\s*(?:см|cm|куб)", vol)
    if cc:
        out["de_volume"] = re.sub(r"\D", "", cc.group(1))
    else:
        lit = re.search(r"\d+[.,]\d+", vol)
        if lit:
            out["de_volume"] = str(int(round(float(lit.group(0).replace(",", ".")) * 1000)))
    km = re.sub(r"\D", "", str(out.get("mileage") or ""))
    if km:
        out["de_km"] = f"{int(km):,}".replace(",", " ")
    if out.get("sum_car") and not out.get("sum_invoice"):       # договор таможенного представителя идёт следом за основным
        try:
            out["sum_invoice"] = re.sub(r"\s*00 коп\.\s*$", "", money_cell(out["sum_car"]))
        except Exception:
            out["sum_invoice"] = out["sum_car"]
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
    # --- паспорт, распознанный без подписей граф («Фамилия», «выдан» машина часто не видит)
    passport_like = bool(re.search(r"российская федерация|мвд|уфмс|овд |паспорт", low))
    if "passport" not in out and passport_like:
        m = re.search(r"(?<![\d.])(\d{2})\s(\d{2})\s(\d{6})(?![\d.])", one)
        if m:
            out["passport"] = f"{m.group(1)} {m.group(2)} {m.group(3)}"
    code = re.search(r"(?<!\d)(\d{2}[.\s]\d{2}[.\s](?:19|20)\d{2})\D{0,24}\d{3}\s?-\s?\d{3}(?!\d)", one)   # дата выдачи стоит перед кодом подразделения
    issue = norm(code.group(1)) if code else ""
    if "birth" not in out and dates:
        m = re.search(r"(?:муж|жен)\w*\.?\D{0,20}(\d{2}[.\s]\d{2}[.\s](?:19|20)\d{2})", one, re.I)
        if m and norm(m.group(1)) != issue:
            out["birth"] = norm(m.group(1))
    if passport_like and not re.search(r"мвд|уфмс|овд|увд|отдел", out.get("passport_issued", "").lower()):
        m = re.search(r"((?:ГУ\s|УМВД|ОМВД|МВД|УФМС|ОУФМС|ТП\s|ОВД|УВД|ОТДЕЛ\w*)[^\d]{6,110}?)(?=\s*(?:\d{2}[.\s]\d{2}[.\s](?:19|20)\d{2}|дата выдачи|код подразделения|личная подпись|$))",
                      one, re.I)
        if m:
            org = re.sub(r"\s+", " ", m.group(1)).strip(" :,.-")
            when = issue or out.get("passport_issued", "")
            if len(org) >= 8:
                out["passport_issued"] = (org + (" " + when if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", when) else "")).strip()
    if "address" not in out:
        m = re.search(r"зарегистрирован\w*\W{0,6}(.{12,200}?)(?=\s*(?:\d{2}[.\s]\d{2}[.\s](?:19|20)\d{2}|ГУ МВД|УМВД|ОМВД|МВД|УФМС|ОУФМС|отдел|подпись|$))",
                      one, re.I)
        if m and re.search(r"ул\.|улица|пр-т|д\.\s?\d|дом |кв\.|г\. ?[А-ЯЁ]", m.group(1)):
            out["address"] = re.sub(r"\s+", " ", m.group(1)).strip(" ,.;")
    return out
