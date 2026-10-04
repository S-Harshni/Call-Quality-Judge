"""Parse spoken Indian amounts ("1.5 crore", "dedh lakh", "पचास लाख", "80k", "२८ लाख") from a customer turn.

Small models often get Indian units wrong (1.5 crore -> 15 lakh). The flow engine uses these parsed amounts as a
deterministic check: if the model's number is off from a spoken amount by a factor of 10 or 100, the spoken amount wins.
"""
import re

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
WORDS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7, "aath": 8, "nau": 9,
    "das": 10, "bees": 20, "pachees": 25, "pachchees": 25, "tees": 30, "paintees": 35, "chalis": 40, "chaalees": 40,
    "paintalis": 45, "pachas": 50, "pachattar": 75, "pachhattar": 75, "pachpan": 55, "pachaas": 50, "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90, "sau": 100,
    "dedh": 1.5, "dhai": 2.5, "dhaai": 2.5, "aadha": 0.5, "half": 0.5,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "दस": 10, "बीस": 20, "पच्चीस": 25, "तीस": 30, "पैंतीस": 35,
    "चालीस": 40, "पैंतालीस": 45, "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90, "सौ": 100, "डेढ़": 1.5, "ढाई": 2.5,
}
UNITS = {
    "crore": "crore", "cr": "crore", "करोड़": "crore", "करोड": "crore",
    "lakh": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh", "laakh": "lakh", "लाख": "lakh",
    "thousand": "thousand", "hazaar": "thousand", "hazar": "thousand", "hajar": "thousand", "हज़ार": "thousand", "हजार": "thousand", "k": "thousand",
    "rupees": "rupees", "rupee": "rupees", "rs": "rupees", "rupaye": "rupees", "rupay": "rupees", "रुपये": "rupees", "रुपए": "rupees",
}
TOKEN = re.compile(r"\d+(?:\.\d+)?k\b|\d+(?:\.\d+)?|[a-z]+|[\u0900-\u097F]+")


UNITS_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TENS_WORDS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def _join_number_words(toks: list[str]) -> list[str]:
    """'ninety five' -> '95', 'one point two' -> '1.2', so spoken English numbers parse like digits."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t in TENS_WORDS and i + 1 < len(toks) and toks[i + 1] in UNITS_WORDS:
            out.append(str(TENS_WORDS[t] + UNITS_WORDS[toks[i + 1]]))
            i += 2
            continue
        if t in UNITS_WORDS and i + 2 < len(toks) and toks[i + 1] == "point" and toks[i + 2] in UNITS_WORDS:
            out.append(f"{UNITS_WORDS[t]}.{UNITS_WORDS[toks[i + 2]]}")
            i += 3
            continue
        out.append(t)
        i += 1
    return out


def amounts(text: str) -> list[tuple[float, str]]:
    """All (value, unit) pairs spoken in the text, e.g. [(1.5, "crore"), (2.2, "lakh")]."""
    toks = _join_number_words(TOKEN.findall(text.translate(DEVANAGARI_DIGITS).lower().replace(",", "")))
    found, where = [], []
    for i, tok in enumerate(toks):
        if re.fullmatch(r"\d+(\.\d+)?k", tok):
            found.append((float(tok[:-1]), "thousand"))
            where.append(i)
            continue
        value = float(tok) if re.fullmatch(r"\d+(\.\d+)?", tok) else WORDS.get(tok)
        if value is None:
            continue
        for nxt in toks[i + 1:i + 3]:  # allow one filler word: "50 ke lakh" is rare, "50 lakh rupees" common
            if nxt in UNITS:
                if UNITS[nxt] != "rupees" or value >= 1000:  # "52000 rupees" counts, "5 rupees" does not
                    found.append((value, UNITS[nxt]))
                    where.append(i)
                break
    # "ek lakh 50 thousand" / "1 crore 20 lakh": merge a bigger unit directly followed by a smaller one
    merged, i = [], 0
    while i < len(found):
        v, u = found[i]
        if i + 1 < len(found) and where[i + 1] - where[i] <= 3 and (u, found[i + 1][1]) in (("lakh", "thousand"), ("crore", "lakh")):
            nv, nu = found[i + 1]
            merged.append((v + nv / 100, u))
            i += 2
            continue
        merged.append((v, u))
        i += 1
    return merged


SCALE = {"crore": 10_000_000, "lakh": 100_000, "thousand": 1_000, "rupees": 1}
FIELDS = {  # field -> (rupees per unit of the field, plausible range in field units)
    "loan_amount_lakh": (100_000, (3, 2_000)),
    "monthly_income_k": (1_000, (3, 2_000)),
}


def reconcile(field: str, model_value: float, said: str) -> float:
    """Let code, not the model, read the number. The model decides which field an amount belongs to; if the
    customer spoke exactly one amount that fits the field's plausible range, that amount is used."""
    if field not in FIELDS or not said:
        return model_value
    per_unit, (lo, hi) = FIELDS[field]
    spoken = {round(v * SCALE[u] / per_unit, 2) for v, u in amounts(said)}
    if not spoken or any(abs(s - model_value) < 1e-6 for s in spoken):
        return model_value
    fits = [s for s in spoken if lo <= s <= hi]
    return fits[0] if len(fits) == 1 else model_value
