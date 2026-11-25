# -*- coding: utf-8 -*-
"""Расчёт рассрочки и приложение к договору с графиком платежей. Без Qt.

Два вида графика:
  annuity  — аннуитетная: платёж каждый месяц одинаковый;
  standard — стандартная (дифференцированная): долг гасится равными частями, проценты — на остаток.
Ставка может быть 0 %. Льготный период: первые N месяцев своя ставка (обычно 0 %), дальше — основная;
при аннуитете платёж пересчитывается на остаток срока в момент смены ставки.
"""
import copy
import io
import re
from decimal import Decimal, ROUND_HALF_UP

KINDS = (("annuity", "аннуитетная — платёж одинаковый"), ("standard", "стандартная — долг равными частями"))
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _d(value):
    if isinstance(value, Decimal):
        return value
    s = str(value if value is not None else "").replace(" ", "").replace(" ", "").replace(",", ".").replace("%", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def r2(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(x, sep=" "):
    """«1 207 500,00»."""
    x = r2(x)
    whole, frac = f"{x:.2f}".split(".")
    neg = whole.startswith("-")
    whole = whole.lstrip("-")
    parts = []
    while len(whole) > 3:
        parts.insert(0, whole[-3:])
        whole = whole[:-3]
    parts.insert(0, whole)
    return ("-" if neg else "") + sep.join(parts) + "," + frac


def months_text(n):
    n10, n100 = n % 10, n % 100
    word = "месяц" if n10 == 1 and n100 != 11 else "месяца" if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else "месяцев"
    return f"{n} {word}"


def pct(x):
    x = Decimal(x).normalize()
    s = f"{x:f}"
    return (s.rstrip("0").rstrip(".") if "." in s else s).replace(".", ",") + "%"


def calculate(amount, months, rate, kind="annuity", grace_months=0, grace_rate=0):
    """График платежей. amount — сумма в рассрочку, rate и grace_rate — % годовых.

    Возвращает {"error": ""} и rows: [{"n", "debt", "principal", "interest", "payment", "rate"}], итоги."""
    res = {"error": ""}
    P, r_main, r_grace = _d(amount), _d(rate), _d(grace_rate)
    try:
        n, g = int(str(months).strip() or 0), int(str(grace_months).strip() or 0)
    except ValueError:
        n, g = 0, 0
    if P is None or P <= 0:
        res["error"] = "укажите сумму в рассрочку"
    elif n <= 0 or n > 360:
        res["error"] = "укажите срок в месяцах (от 1 до 360)"
    elif r_main is None or r_main < 0 or r_main > 200:
        res["error"] = "укажите ставку, % годовых (можно 0)"
    elif g < 0 or g >= n and g:
        res["error"] = "льготный период должен быть короче общего срока"
    elif g and (r_grace is None or r_grace < 0):
        res["error"] = "укажите ставку льготного периода (можно 0)"
    elif kind not in ("annuity", "standard"):
        res["error"] = "неизвестный вид графика"
    if res["error"]:
        return res
    P = r2(P)
    rate_of = lambda k: (r_grace if g and k <= g else r_main) / Decimal(1200)      # месячная ставка для месяца k
    rows, bal = [], P
    part = r2(P / n)                                   # стандартная: равная доля долга
    pay = None
    for k in range(1, n + 1):
        r = rate_of(k)
        interest = r2(bal * r)
        if kind == "standard":
            principal = bal if k == n else min(bal, part)
        else:
            if pay is None or (g and k == g + 1):      # начало срока или смена ставки — платёж на остаток срока
                m = n - k + 1
                pay = r2(bal / m) if r == 0 else r2(bal * r / (1 - (1 + r) ** (-m)))
            principal = bal if k == n else min(bal, pay - interest)
        payment = principal + interest
        rows.append({"n": k, "debt": bal, "principal": principal, "interest": interest, "payment": payment,
                     "rate": (r_grace if g and k <= g else r_main)})
        bal = r2(bal - principal)
    res.update(rows=rows, amount=P, months=n, kind=kind, rate=r_main, grace_months=g, grace_rate=r_grace if g else None,
               total=sum((x["payment"] for x in rows), Decimal(0)), interest_total=sum((x["interest"] for x in rows), Decimal(0)),
               principal_total=sum((x["principal"] for x in rows), Decimal(0)))
    return res


def rate_phrase(res):
    """«0% годовых» или «0% годовых первые 12 месяцев, далее 5% годовых»."""
    if res.get("grace_months"):
        return f"{pct(res['grace_rate'])} годовых первые {months_text(res['grace_months'])}, далее {pct(res['rate'])} годовых"
    return f"{pct(res['rate'])} годовых"


def payment_phrase(res):
    """Как назвать платёж в месяц одной строкой."""
    rows = res["rows"]
    pays = [x["payment"] for x in rows]
    body = pays[:-1] or pays                           # последний платёж закрывает копейки
    if res["kind"] == "standard" and len(set(pays)) > 1:
        return f"от {money(min(pays))} ₽ до {money(max(pays))} ₽ (уменьшается каждый месяц)"
    g = res.get("grace_months") or 0
    if g and len(set(body)) > 1:
        return f"{money(rows[0]['payment'])} ₽ первые {months_text(g)}, далее {money(rows[g]['payment'])} ₽"
    return f"{money(body[0])} ₽"


HEAD_FILL = "FDF4EC"       # шапка таблицы платежей — бледно-персиковая
TOTAL_FILL = "EDF7EE"      # строка «Итого» — бледно-зелёная


def summary(res):
    if res.get("error"):
        return ""
    kind = dict(KINDS)[res["kind"]].split(" — ")[0]
    lines = [f"Рассрочка {kind}: {money(res['amount'])} ₽ на {months_text(res['months'])} под {rate_phrase(res)}",
             f"Платёж в месяц: {payment_phrase(res)}",
             f"Проценты за весь срок: {money(res['interest_total'])} ₽",
             f"Сумма всех платежей: {money(res['total'])} ₽", "",
             "Месяц\tОстаток долга\tПогашение долга\tПроценты\tПлатёж"]
    for x in res["rows"]:
        lines.append(f"{x['n']}\t{money(x['debt'])}\t{money(x['principal'])}\t{money(x['interest'])}\t{money(x['payment'])}")
    lines.append(f"Итого\t\t{money(res['principal_total'])}\t{money(res['interest_total'])}\t{money(res['total'])}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- приложение к договору (Word)
def _set_par(par, text):
    """Текст абзаца целиком, с оформлением его первого куска."""
    runs = list(par.runs)
    if not runs:
        par.add_run(text)
        return
    for br in runs[0]._r.findall(f"{{{W}}}br"):
        runs[0]._r.remove(br)
    runs[0].text = text
    for r in runs[1:]:
        r._r.getparent().remove(r._r)


def _table(doc, res, font_pt=9.5):
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    head = ("Месяц", "Остаток долга", "Погашение долга", "Проценты", "Платёж в месяц")
    rows = res["rows"]
    t = doc.add_table(rows=len(rows) + 2, cols=len(head))
    t.alignment = 1
    pr = t._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "808080")
        borders.append(e)
    pr.append(borders)

    def put(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.RIGHT):
        p = cell.paragraphs[0]
        p.alignment = align
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(font_pt)
        run.font.name = "Times New Roman"
        run._r.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "Times New Roman")
        run.font.color.rgb = RGBColor(0, 0, 0)

    for c, title in enumerate(head):
        put(t.cell(0, c), title, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    trpr = t.rows[0]._tr.get_or_add_trPr()
    rep = OxmlElement("w:tblHeader")                    # шапка повторяется на каждой странице
    rep.set(qn("w:val"), "true")
    trpr.append(rep)
    for k, x in enumerate(rows, 1):
        put(t.cell(k, 0), str(x["n"]), align=WD_ALIGN_PARAGRAPH.CENTER)
        for c, key in enumerate(("debt", "principal", "interest", "payment"), 1):
            put(t.cell(k, c), money(x[key]))
    last = len(rows) + 1

    def shade(row, color):                              # бледная заливка строки: шапка и итог
        for cell in t.rows[row].cells:
            tcpr = cell._tc.get_or_add_tcPr()
            sh = OxmlElement("w:shd")
            sh.set(qn("w:val"), "clear")
            sh.set(qn("w:color"), "auto")
            sh.set(qn("w:fill"), color)
            tcpr.append(sh)

    shade(0, HEAD_FILL)
    shade(last, TOTAL_FILL)
    put(t.cell(last, 0), "Итого", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    put(t.cell(last, 2), money(res["principal_total"]), bold=True)
    put(t.cell(last, 3), money(res["interest_total"]), bold=True)
    put(t.cell(last, 4), money(res["total"]), bold=True)
    return t


def build_docx(template, data, res, out_path):
    """Приложение с расчётом рассрочки. template — путь или байты бланка; data: contract_no, contract_date
    («16 сентября 2026»), cost, customs, first — числа или строки; res — результат calculate()."""
    import docx
    doc = docx.Document(io.BytesIO(template) if isinstance(template, (bytes, bytearray)) else template)
    kind = dict(KINDS)[res["kind"]].split(" — ")[0]
    num = lambda v: money(_d(v)) if _d(v) is not None else ""
    anchor = None
    for p in list(doc.paragraphs):
        t = p.text.strip()
        if t.startswith("Приложение №") and "к Договору" in t:
            m = re.match(r"(Приложение № \d+)", t)
            date = str(data.get("contract_date") or "").strip()
            _set_par(p, f"{m.group(1) if m else 'Приложение № 2'} к Договору № {data.get('contract_no') or '____'} от "
                        + (f"{date} года" if date else "«__» ________ 20__ года"))
        elif t.startswith("Стоимость транспортного средства"):
            _set_par(p, f"Стоимость транспортного средства составляет {num(data.get('cost'))} российских рублей."
                     if num(data.get("cost")) else "")
        elif t.startswith("Таможенная пошлина"):
            _set_par(p, f"Таможенная пошлина – {num(data.get('customs'))} российских рублей." if num(data.get("customs")) else "")
        elif t.startswith("Сумма первого взноса"):
            _set_par(p, f"Сумма первого взноса – {num(data.get('first'))} российских рублей." if num(data.get("first")) else "")
        elif re.match(r"Сумма [\d\s ,]+российских рублей в рассрочку", t):
            _set_par(p, f"Сумма {money(res['amount'])} российских рублей в рассрочку под {rate_phrase(res)} "
                        f"на {months_text(res['months'])}.")
        elif t.startswith("Сумма платежа в месяц"):
            _set_par(p, f"Сумма платежа в месяц: {payment_phrase(res)}")
        elif t.startswith("Сумма рассрочки"):
            _set_par(p, f"Сумма рассрочки: {money(res['amount'])} ₽")
        elif t.startswith("Сумма всех платежей"):
            _set_par(p, f"Сумма всех платежей: {money(res['total'])} ₽")
        elif t.startswith("Установленный срок рассрочки"):
            _set_par(p, f"Установленный срок рассрочки: {months_text(res['months'])}")
            extra = copy.deepcopy(p._p)
            p._p.addnext(extra)
            from docx.text.paragraph import Paragraph
            _set_par(Paragraph(extra, p._parent), f"Ставка рассрочки: {rate_phrase(res).replace(' годовых', ' в год')}")
        elif t.startswith("График платежей"):
            _set_par(p, "График платежей")
            from docx.shared import Pt
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(4)
            anchor = p
    for p in list(doc.paragraphs):                       # картинка-образец графика из бланка не нужна
        if p._p.findall(f".//{{{W}}}drawing"):
            p._p.getparent().remove(p._p)
    tbl = _table(doc, res)
    if anchor is not None:
        anchor._p.addnext(tbl._tbl)
    doc.save(out_path)
    return out_path


def selftest():
    D = Decimal
    r = calculate("845250", 23, 0)                       # пример из приложения: 0 %, 23 месяца
    assert not r["error"] and len(r["rows"]) == 23 and all(x["payment"] == D("36750.00") for x in r["rows"])
    assert r["total"] == D("845250.00") and r["interest_total"] == 0 and r["rows"][-1]["debt"] == D("36750.00")
    assert payment_phrase(r) == "36 750,00 ₽" and rate_phrase(r) == "0% годовых" and months_text(23) == "23 месяца"
    r = calculate("300000", 24, 5, "annuity", 12, 0)     # 12 месяцев под 0 %, дальше 5 %
    assert r["rows"][0]["payment"] == D("12500.00") and r["rows"][11]["interest"] == 0 and r["rows"][12]["debt"] == D("150000.00")
    assert r["rows"][12]["payment"] == D("12841.12") and r["rows"][12]["interest"] == D("625.00"), r["rows"][12]
    assert r["principal_total"] == D("300000.00") and r["total"] == r["principal_total"] + r["interest_total"]
    assert "первые 12 месяцев, далее 5% годовых" in rate_phrase(r) and "далее 12 841,12 ₽" in payment_phrase(r)
    r = calculate("300000", 24, 5, "standard", 12, 0)
    assert all(x["principal"] == D("12500.00") for x in r["rows"]) and r["rows"][12]["interest"] == D("625.00")
    assert r["rows"][-1]["interest"] == D("52.08") and r["rows"][11]["payment"] == D("12500.00")
    r = calculate("100000", 12, 12, "annuity")
    assert r["rows"][0]["payment"] == D("8884.88") and r["principal_total"] == D("100000.00") and abs(r["rows"][-1]["payment"] - D("8884.88")) < 1
    r = calculate("100000", 3, 0, "standard")            # копейки уходят в последний платёж
    assert [x["principal"] for x in r["rows"]] == [D("33333.33"), D("33333.33"), D("33333.34")]
    assert calculate("", 12, 0)["error"] and calculate("1000", 0, 0)["error"] and calculate("1000", 12, 5, "annuity", 12, 0)["error"]
    assert money("1207500") == "1 207 500,00" and pct("5.50") == "5,5%" and months_text(11) == "11 месяцев"
    assert "Итого" in summary(calculate("845250", 23, 0))
    return True


if __name__ == "__main__":
    print(selftest())
