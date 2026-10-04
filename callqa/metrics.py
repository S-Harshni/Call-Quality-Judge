"""Agreement between judge verdicts and reference labels (the positive class is FAIL)."""


def confusion(pred: list[bool], gold: list[bool]) -> dict:
    tp = sum(p and g for p, g in zip(pred, gold))
    fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold))
    tn = len(gold) - tp - fp - fn
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def scores(pred: list[bool], gold: list[bool]) -> dict:
    c = confusion(pred, gold)
    n = len(gold) or 1
    prec = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
    rec = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if c["tp"] + c["fn"] else None)
    acc = (c["tp"] + c["tn"]) / n
    return {**c, "precision": prec, "recall": rec, "f1": f1, "accuracy": acc, "kappa": kappa(pred, gold)}


def kappa(pred: list[bool], gold: list[bool]) -> float | None:
    """Cohen's kappa: agreement corrected for chance."""
    n = len(gold)
    if not n:
        return None
    po = sum(p == g for p, g in zip(pred, gold)) / n
    pp, pg = sum(pred) / n, sum(gold) / n
    pe = pp * pg + (1 - pp) * (1 - pg)
    return None if pe == 1 else (po - pe) / (1 - pe)
