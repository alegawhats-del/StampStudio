# -*- coding: utf-8 -*-
"""Предварительный расчёт таможенных платежей за легковой автомобиль для личного пользования
(единые ставки ЕАЭС). Суммы вводятся в российских рублях, пересчёт — по курсам Нацбанка РБ. Без Qt.

Это калькулятор для оценки: он считает деньги и ничего не оформляет.
"""
import datetime
from decimal import Decimal, ROUND_HALF_UP

FEE_BYN = "120.00"                       # сбор за таможенные операции, легковой автомобиль

# евро за 1 см³: (объём до, ставка)
RATES_3_5 = [(1000, "1.5"), (1500, "1.7"), (1800, "2.5"), (2300, "2.7"), (3000, "3.0"), (None, "3.6")]
RATES_OVER_5 = [(1000, "3.0"), (1500, "3.2"), (1800, "3.5"), (2300, "4.8"), (3000, "5.0"), (None, "5.7")]
# моложе 3 лет: (стоимость в евро до, процент, но не менее евро за 1 см³)
RATES_UNDER_3 = [(8500, "54", "2.5"), (16700, "48", "3.5"), (42300, "48", "5.5"), (84500, "48", "7.5"),
                 (169000, "48", "15"), (None, "48", "20")]

AGE_TITLES = {"under3": "моложе 3 лет", "3to5": "от 3 до 5 лет", "over5": "старше 5 лет"}


def _d(value):
    """Число из строки «1 234,56» / «1234.56». None, если не число."""
    if isinstance(value, Decimal):
        return value
    s = str(value if value is not None else "").replace(" ", "").replace(" ", "").replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None


def r2(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(x):
    """«37491.14» — точка, два знака, без пробелов."""
    return "" if x is None else f"{r2(x):.2f}"


def parse_date(text):
    s = str(text or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _add_years(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:                       # 29 февраля
        return d.replace(year=d.year + n, day=28)


def age_of(made, on_date):
    """(категория, лет, месяцев). Категория: under3 — меньше 3 лет; 3to5 — от 3 до 5 лет включительно; over5."""
    if made is None or on_date is None or made > on_date:
        return "", 0, 0
    months = (on_date.year - made.year) * 12 + on_date.month - made.month - (1 if on_date.day < made.day else 0)
    if on_date < _add_years(made, 3):
        cat = "under3"
    elif on_date <= _add_years(made, 5):
        cat = "3to5"
    else:
        cat = "over5"
    return cat, months // 12, months % 12


def age_text(years, months):
    def plural(n, forms):
        n10, n100 = n % 10, n % 100
        return forms[0] if n10 == 1 and n100 != 11 else forms[1] if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else forms[2]
    out = f"{years} {plural(years, ('год', 'года', 'лет'))}"
    if months:
        out += f" {months} мес."
    return out


def per_cc(table, volume):
    for limit, rate in table:
        if limit is None or volume <= limit:
            return Decimal(rate)
    return Decimal(table[-1][1])


def calculate(price_rub, volume, made, on_date, eur_byn, rub100_byn, paid_rub=None, fee_byn=FEE_BYN):
    """Посчитать платежи. Все денежные входы — строки или числа; даты — datetime.date или «ДД.ММ.ГГГГ».

    Возвращает словарь; res["error"] не пуст, если данных не хватает."""
    res = {"error": ""}
    price_rub, eur_byn, rub100 = _d(price_rub), _d(eur_byn), _d(rub100_byn)
    fee = _d(fee_byn) or Decimal(0)
    vol = _d(volume)
    made = parse_date(made) if not isinstance(made, datetime.date) else made
    on_date = parse_date(on_date) if not isinstance(on_date, datetime.date) else on_date
    if on_date is None:
        res["error"] = "укажите дату расчёта"
    elif made is None:
        res["error"] = "укажите дату выпуска автомобиля"
    elif made > on_date:
        res["error"] = "дата выпуска позже даты расчёта"
    elif vol is None or vol <= 0 or vol != vol.to_integral_value():
        res["error"] = "укажите объём двигателя в см³ (целое число)"
    elif price_rub is None or price_rub <= 0:
        res["error"] = "укажите стоимость автомобиля в российских рублях"
    elif eur_byn is None or eur_byn <= 0 or rub100 is None or rub100 <= 0:
        res["error"] = "нужны курсы: 1 EUR и 100 RUB в белорусских рублях"
    if res["error"]:
        return res
    vol = int(vol)
    rub_byn = rub100 / Decimal(100)
    cat, years, months = age_of(made, on_date)
    price_eur = r2(price_rub * rub_byn / eur_byn)
    price_byn = r2(price_eur * eur_byn)                 # строго через округлённые евро: сходится до копейки
    if cat == "under3":
        row = next(r for r in RATES_UNDER_3 if r[0] is None or price_eur <= r[0])
        pct, floor = Decimal(row[1]), Decimal(row[2])
        by_pct = r2(price_eur * pct / Decimal(100))
        by_cc = r2(Decimal(vol) * floor)
        if by_cc > by_pct:
            duty_eur, rate_text, basis = by_cc, f"{floor.normalize():f} EUR за 1 см³ (минимум)", "объём двигателя"
        else:
            duty_eur, rate_text, basis = by_pct, f"{pct.normalize():f} % от стоимости", "стоимость"
        rate_eur = floor
    else:
        rate_eur = per_cc(RATES_3_5 if cat == "3to5" else RATES_OVER_5, vol)
        duty_eur = r2(Decimal(vol) * rate_eur)
        rate_text, basis = f"{rate_eur.normalize():f} EUR за 1 см³", "объём двигателя"
    duty_byn = r2(duty_eur * eur_byn)
    total_byn = r2(duty_byn + fee)
    res.update(age=cat, age_title=AGE_TITLES[cat], years=years, months=months, volume=vol,
               price_rub=r2(price_rub), price_eur=price_eur, price_byn=price_byn,
               rate_text=rate_text, basis=basis, duty_eur=duty_eur, duty_byn=duty_byn,
               duty_rub=r2(duty_byn / rub_byn), fee_byn=r2(fee), fee_rub=r2(fee / rub_byn),
               total_byn=total_byn, total_rub=r2(total_byn / rub_byn),
               eur_byn=eur_byn, rub100_byn=rub100)
    paid = _d(paid_rub)
    if paid is not None and paid > 0:
        paid_byn = r2(paid * rub_byn)
        res.update(paid_rub=r2(paid), paid_byn=paid_byn, paid_eur=r2(paid_byn / eur_byn),
                   diff_byn=r2(paid_byn - duty_byn), diff_rub=r2(paid - res["duty_rub"]))
    return res


def summary(res, on_date=""):
    """Текст расчёта — для копирования клиенту или в заметки."""
    if res.get("error"):
        return ""
    lines = ["Предварительный расчёт таможенных платежей" + (f" на {on_date}" if on_date else ""),
             f"Курс НБ РБ: 1 EUR = {res['eur_byn']} BYN, 100 RUB = {res['rub100_byn']} BYN",
             f"Автомобиль: {age_text(res['years'], res['months'])} ({res['age_title']}), {res['volume']} см³",
             f"Стоимость: {money(res['price_rub'])} RUB = {money(res['price_eur'])} EUR = {money(res['price_byn'])} BYN",
             f"Ставка пошлины: {res['rate_text']}",
             f"Пошлина: {money(res['duty_eur'])} EUR = {money(res['duty_byn'])} BYN = {money(res['duty_rub'])} RUB",
             f"Таможенный сбор: {money(res['fee_byn'])} BYN = {money(res['fee_rub'])} RUB",
             f"Итого: {money(res['total_byn'])} BYN = {money(res['total_rub'])} RUB"]
    if "paid_rub" in res:
        sign = "больше" if res["diff_byn"] > 0 else "меньше"
        lines.append(f"Уплачено: {money(res['paid_rub'])} RUB = {money(res['paid_byn'])} BYN — "
                     + ("совпадает с расчётом" if res["diff_byn"] == 0 else
                        f"на {money(abs(res['diff_byn']))} BYN {sign} пошлины по тарифу"))
    lines.append("Расчёт предварительный; точную сумму определяет таможня.")
    return "\n".join(lines)


def selftest():
    D = datetime.date
    assert age_of(D(2022, 4, 12), D(2026, 11, 16))[0] == "3to5"
    assert age_of(D(2021, 11, 16), D(2026, 11, 16))[0] == "3to5" and age_of(D(2021, 11, 15), D(2026, 11, 16))[0] == "over5"
    assert age_of(D(2023, 11, 17), D(2026, 11, 16))[0] == "under3" and age_of(D(2023, 11, 16), D(2026, 11, 16))[0] == "3to5"
    assert per_cc(RATES_3_5, 1968) == Decimal("2.7") and per_cc(RATES_3_5, 1000) == Decimal("1.5")
    assert per_cc(RATES_OVER_5, 2301) == Decimal("5.0") and per_cc(RATES_3_5, 3001) == Decimal("3.6")
    # 11300 EUR при курсах 3.3178 и 3.6179: цена в рублях подобрана под эти евро
    r = calculate("1036268", 1968, "12.04.2022", "16.11.2026", "3.3178", "3.6179", paid_rub="490000")
    assert not r["error"] and r["age"] == "3to5" and r["rate_text"] == "2.7 EUR за 1 см³"
    assert money(r["price_eur"]) == "11300.00" and money(r["price_byn"]) == "37491.14"
    assert money(r["duty_eur"]) == "5313.60" and money(r["duty_byn"]) == "17629.46"
    assert money(r["total_byn"]) == "17749.46" and r["price_byn"] == r2(r["price_eur"] * Decimal("3.3178"))
    assert "paid_byn" in r and r["diff_byn"] == r2(r["paid_byn"] - r["duty_byn"])
    r = calculate("3000000", 1968, "01.06.2025", "16.11.2026", "3.3178", "3.6179")
    assert r["age"] == "under3" and r["rate_text"].startswith("48 %")
    r = calculate("300000", 1968, "01.06.2025", "16.11.2026", "3.3178", "3.6179")
    assert "минимум" in r["rate_text"] and money(r["duty_eur"]) == "4920.00"
    r = calculate("1000000", 2500, "01.06.2015", "16.11.2026", "3.3178", "3.6179")
    assert r["age"] == "over5" and money(r["duty_eur"]) == "12500.00"
    assert calculate("", 1968, "12.04.2022", "16.11.2026", "3.3", "3.6")["error"]
    assert calculate("100", "1968.5", "12.04.2022", "16.11.2026", "3.3", "3.6")["error"]
    assert "Итого" in summary(calculate("1036268", 1968, "12.04.2022", "16.11.2026", "3.3178", "3.6179"), "16.11.2026")
    assert age_text(4, 7) == "4 года 7 мес." and age_text(5, 0) == "5 лет" and age_text(1, 0) == "1 год"
    return True


if __name__ == "__main__":
    print(selftest())
