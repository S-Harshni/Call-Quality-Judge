"""Build the evaluation set once and save it, so every judge configuration sees exactly the same transcripts and labels.

real      all 156 calls from the voice agent, labelled from what its code logged
injected  7 defect types x 18 clean calls (6 per language), one known defect each
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from callqa.labels import DEFECTS, answer_json, inject, real_labels, repeatable  # noqa: E402
from callqa.transcript import load_db  # noqa: E402


def dump(call, labels, subset, evidence=None):
    return {"id": call.call_id, "subset": subset, "meta": {k: v for k, v in call.meta.items() if k != "violations"},
            "turns": [{"speaker": t.speaker, "text": t.text, "lang": t.lang} for t in call.turns], "labels": labels, "evidence": evidence}


def main() -> None:
    rng = random.Random(7)
    calls = load_db(ROOT / "data" / "calls.db")
    rows = [dump(c, real_labels(c), "real") for c in calls]
    clean = [c for c in calls if not any(real_labels(c).values())]
    by_lang = {lang: [c for c in clean if c.meta["language"] == lang] for lang in ("en", "hinglish", "hi")}
    # Two calls are held out as few-shot examples and never used as injection bases.
    ex_clean, ex_base = by_lang["en"][0], by_lang["hinglish"][0]
    ex_call, ex_labels, ex_ev = inject(ex_base, "repeat_question", random.Random(1))
    examples = [dump(ex_call, ex_labels, "example", ex_ev) | {"answer": answer_json(ex_labels, ex_ev)},
                dump(ex_clean, real_labels(ex_clean), "example") | {"answer": answer_json(real_labels(ex_clean))}]
    # Bases need at least two agent turns, so a defect is never written into the closing line.
    pool = {lang: [c for c in cs if c not in (ex_clean, ex_base) and len(c.agent_turns()) >= 2] for lang, cs in by_lang.items()}
    for defect in DEFECTS:
        for lang in ("en", "hinglish", "hi"):
            bases = [c for c in pool[lang] if repeatable(c)] if defect == "repeat_question" else pool[lang]
            for base in rng.sample(bases, 6):
                c, labels, ev = inject(base, defect, rng)
                rows.append(dump(c, labels, "injected", ev))
    held_out = {ex_clean.call_id, ex_base.call_id}
    out = {"examples": examples, "held_out_real_ids": sorted(held_out), "rows": rows}
    (ROOT / "data" / "eval_set.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)} transcripts ({sum(r['subset'] == 'real' for r in rows)} real, {sum(r['subset'] == 'injected' for r in rows)} injected)")


if __name__ == "__main__":
    main()
