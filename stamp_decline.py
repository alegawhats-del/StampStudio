# -*- coding: utf-8 -*-
"""Склонение по падежам: ФИО, должности, названия. Без Qt.

ФИО склоняются по правилам (petrovich), обычные слова и словосочетания — по словарю
(pymorphy3). В словосочетании меняется только главная часть в именительном падеже:
«общество с ограниченной ответственностью» → «обществу с ограниченной ответственностью».
"""
import re

CASES = [("nomn", "И", "кто, что?", "именительный"),
         ("gent", "Р", "кого, чего?", "родительный"),
         ("datv", "Д", "кому, чему?", "дательный"),
         ("accs", "В", "кого, что?", "винительный"),
         ("ablt", "Т", "кем, чем?", "творительный"),
         ("loct", "П", "о ком, о чём?", "предложный")]

GENDERS = [("", "определить"), ("m", "мужской"), ("f", "женский")]

_PATR_M = ("вич", "ьич", "ич", "оглы", "улы", "уулу")
_PATR_F = ("вна", "чна", "шна", "кызы", "гызы", "кизи")
_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)

_morph = None
_petr = None


def _analyzer():
    """Словарь русского языка; None, если его нет в сборке."""
    global _morph
    if _morph is None:
        try:
            import pymorphy3
            import pymorphy3_dicts_ru
            _morph = pymorphy3.MorphAnalyzer(path=pymorphy3_dicts_ru.get_path(), lang="ru")
        except Exception:
            _morph = False
    return _morph or None


def _petrovich():
    global _petr
    if _petr is None:
        try:
            from petrovich.main import Petrovich
            _petr = Petrovich()
        except Exception:
            _petr = False
    return _petr or None


def available():
    """(ФИО, слова) — что из склонения работает в этой сборке."""
    return _petrovich() is not None, _analyzer() is not None


def _like(src, word):
    """Вернуть слову регистр исходного: ИВАНОВ → ИВАНОВА, Иванов → Иванова."""
    if not word:
        return word
    if src.isupper() and len(src) > 1:
        return word.upper()
    if src[:1].isupper():
        return "-".join(p[:1].upper() + p[1:] for p in word.split("-")) if "-" in src else word[:1].upper() + word[1:]
    return word


def patronymic_gender(word):
    w = word.lower()
    if w.endswith(_PATR_F):
        return "f"
    if w.endswith(_PATR_M):
        return "m"
    return ""


def _name_gender(word):
    m = _analyzer()
    if m is None:
        return ""
    for p in m.parse(word)[:4]:
        if "Name" in p.tag:
            return "m" if "masc" in p.tag else "f" if "femn" in p.tag else ""
    return ""


def _is_name(word):
    m = _analyzer()
    return bool(m and any("Name" in p.tag for p in m.parse(word)[:4]))


def split_fio(words):
    """Разобрать 2–3 слова на (фамилия, имя, отчество) с их местами. None — это не ФИО."""
    n = len(words)
    if n not in (2, 3) or not all(w[:1].isupper() for w in words):
        return None
    patr = [i for i, w in enumerate(words) if patronymic_gender(w)]
    if n == 3:
        if patr and patr[-1] == 2:
            return {"last": 0, "first": 1, "middle": 2}          # Иванов Иван Иванович
        if patr and patr[-1] == 1:
            return {"first": 0, "middle": 1, "last": 2}          # Иван Иванович Иванов
        return None
    if patr and patr[-1] == 1:
        return {"first": 0, "middle": 1}                         # Иван Иванович
    if _is_name(words[0]) and not _is_name(words[1]):
        return {"first": 0, "last": 1}                           # Иван Иванов
    if _is_name(words[1]):
        return {"last": 0, "first": 1}                           # Иванов Иван
    return None


def _fio_forms(words, parts, gender):
    from petrovich.enums import Case, Gender
    p = _petrovich()
    g = {"m": Gender.MALE, "f": Gender.FEMALE}.get(gender, Gender.ANDROGYNOUS)
    cases = {"gent": Case.GENITIVE, "datv": Case.DATIVE, "accs": Case.ACCUSATIVE,
             "ablt": Case.INSTRUMENTAL, "loct": Case.PREPOSITIONAL}
    fn = {"last": p.lastname, "first": p.firstname, "middle": p.middlename}
    out = {"nomn": list(words)}
    for key, case in cases.items():
        res = list(words)
        for part, i in parts.items():
            src = words[i]
            base = src[:1].upper() + src[1:].lower() if src.isupper() else src
            try:
                res[i] = _like(src, fn[part](base, case, g))
            except Exception:
                res[i] = src
        out[key] = res
    return out


def _nomn_parse(m, word):
    for p in m.parse(word)[:6]:
        if "nomn" in p.tag and p.tag.POS in ("NOUN", "ADJF", "PRTF", "NPRO", "NUMR"):
            return p
    return None


def _phrase_forms(words):
    """Склонить главную часть словосочетания: слова в именительном до первого «не именительного»."""
    m = _analyzer()
    out = {c[0]: list(words) for c in CASES}
    if m is None:
        return out, False
    head = []
    for i, w in enumerate(words):
        p = _nomn_parse(m, w)
        if p is None:
            break
        head.append((i, p))
        if p.tag.POS in ("NOUN", "NPRO"):
            break                              # дальше идут зависимые слова («директора по логистике»)
    if not head:
        return out, False
    anim = any(p.tag.POS == "NOUN" and "anim" in p.tag for _i, p in head)
    for case in ("gent", "datv", "accs", "ablt", "loct"):
        for i, p in head:
            grams = {case}
            if case == "accs" and p.tag.POS in ("ADJF", "PRTF") and ("masc" in p.tag or "plur" in p.tag):
                grams.add("anim" if anim else "inan")
            f = p.inflect(grams) or p.inflect({case})
            if f is not None:
                out[case][i] = _like(words[i], f.word)
    return out, True


def about_prefix(text):
    """Предлог для предложного падежа: «о» или «об» (перед а, и, о, у, э)."""
    return "об" if text[:1].lower() in "аиоуэ" else "о"


def decline(text, gender=""):
    """Просклонять ФИО, слово или словосочетание.

    Возвращает {"forms": {падеж: строка}, "gender": "m"/"f"/"", "fio": bool, "ok": bool}.
    ok=False — склонять нечем (нет словаря) или в тексте нет слов в именительном падеже."""
    text = " ".join(str(text or "").split())
    res = {"forms": {c[0]: text for c in CASES}, "gender": gender or "", "fio": False, "ok": False}
    if not text:
        return res
    tokens = text.split(" ")
    words = [t for t in tokens if _WORD.fullmatch(t)]
    if len(words) != len(tokens):
        clean = [re.sub(r"^[^\w]+|[^\w]+$", "", t, flags=re.UNICODE) for t in tokens]
    else:
        clean = tokens
    _INIT = re.compile(r"(?:[^\W\d_]\.){1,2}", re.UNICODE)
    inits = [i for i, t in enumerate(tokens) if _INIT.fullmatch(t)]
    rest = [i for i in range(len(tokens)) if i not in inits]
    if inits and len(rest) == 1 and _WORD.fullmatch(tokens[rest[0]]) and tokens[rest[0]][:1].isupper() \
            and _petrovich() is not None:
        i = rest[0]                              # фамилия с инициалами: «Урман А. В.»
        ff = _fio_forms([tokens[i]], {"last": 0}, gender)
        forms = {c[0]: list(tokens) for c in CASES}
        for case in forms:
            forms[case][i] = ff[case][0]
        res.update(forms={case: " ".join(v) for case, v in forms.items()}, fio=True, ok=True)
        return res
    # ФИО целиком или в хвосте («индивидуальный предприниматель Иванов Иван Иванович»)
    fio_at, parts = None, None
    if _petrovich() is not None:
        for size in (3, 2):
            if len(clean) >= size:
                tail = clean[-size:]
                if all(_WORD.fullmatch(w or "") for w in tail):
                    pp = split_fio(tail)
                    if pp:
                        fio_at, parts = len(clean) - size, pp
                        break
    forms = {c[0]: list(tokens) for c in CASES}
    ok = False
    if fio_at is not None:
        tail = clean[fio_at:]
        g = gender
        if not g:
            g = next((patronymic_gender(w) for w in tail if patronymic_gender(w)), "")
        if not g and "first" in parts:
            g = _name_gender(tail[parts["first"]])
        res["gender"] = g
        ff = _fio_forms(tail, parts, g)
        for case in forms:
            for k, w in enumerate(ff[case]):
                forms[case][fio_at + k] = tokens[fio_at + k].replace(clean[fio_at + k], w, 1)
        res["fio"] = fio_at == 0
        ok = True
    head_n = fio_at if fio_at is not None else len(tokens)
    for k in range(head_n):                      # названия в кавычках, сокращения и инициалы не склоняются
        t = tokens[k]
        if t[:1] in "«\"“„'" or t.endswith(".") or len(clean[k]) <= 1 or (clean[k].isupper() and not text.isupper()):
            head_n = k
            break
    if head_n:
        head_words = clean[:head_n]
        pf, done = _phrase_forms(head_words)
        if done:
            ok = True
            for case in forms:
                for k, w in enumerate(pf[case]):
                    forms[case][k] = tokens[k].replace(clean[k], w, 1) if clean[k] else tokens[k]
    res["forms"] = {case: " ".join(v) for case, v in forms.items()}
    res["ok"] = ok
    return res


def selftest():
    fio, words = available()
    assert fio, "нет правил склонения ФИО"
    r = decline("Жидяева Алла Павловна")
    assert r["fio"] and r["gender"] == "f"
    assert r["forms"]["gent"] == "Жидяевой Аллы Павловны"
    assert r["forms"]["datv"] == "Жидяевой Алле Павловне"
    assert r["forms"]["accs"] == "Жидяеву Аллу Павловну"
    assert r["forms"]["ablt"] == "Жидяевой Аллой Павловной"
    r = decline("МОЛЧАНОВ ДМИТРИЙ АНАТОЛЬЕВИЧ")
    assert r["gender"] == "m" and r["forms"]["gent"] == "МОЛЧАНОВА ДМИТРИЯ АНАТОЛЬЕВИЧА"
    r = decline("Дмитрий Анатольевич Молчанов")
    assert r["forms"]["datv"] == "Дмитрию Анатольевичу Молчанову"
    assert about_prefix("Иванове") == "об" and about_prefix("Жидяевой") == "о"
    assert decline("")["ok"] is False
    if words:
        r = decline("генеральный директор")
        assert r["forms"]["gent"] == "генерального директора" and r["forms"]["accs"] == "генерального директора"
        r = decline("Общество с ограниченной ответственностью")
        assert r["forms"]["datv"] == "Обществу с ограниченной ответственностью"
        r = decline("индивидуальный предприниматель Иванов Иван Иванович")
        assert r["forms"]["ablt"] == "индивидуальным предпринимателем Ивановым Иваном Ивановичем"
        assert decline("заместитель директора по логистике")["forms"]["gent"] == "заместителя директора по логистике"
        assert decline("ООО «Бэлкос-М»")["forms"]["gent"] == "ООО «Бэлкос-М»"
        assert decline("Урман А. В.", "m")["forms"]["datv"] == "Урману А. В."
        r = decline("легковой автомобиль")
        assert r["forms"]["accs"] == "легковой автомобиль"
    return True


def selftest_text():
    """Для строки самопроверки сборки: ok / fio-only (нет словаря) / fail:причина."""
    try:
        selftest()
        return "ok" if all(available()) else "fio-only"
    except Exception as e:
        return "fail:" + type(e).__name__


if __name__ == "__main__":
    print(selftest())
