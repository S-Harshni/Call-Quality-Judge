"""Write docs/data.json for the project page from the evaluation results."""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from callqa.rubric import CHECKS  # noqa: E402
from eval.insights import best_config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--author", required=True)
    args = ap.parse_args()
    ev = json.loads((ROOT / "results" / "eval.json").read_text())
    best = best_config(ev)
    data = json.loads((ROOT / "data" / "eval_set.json").read_text(encoding="utf-8"))
    held = set(data["held_out_real_ids"])
    rows = {r["id"]: r for r in data["rows"] if r["id"] not in held}
    preds = {p["id"]: p for p in map(json.loads, (ROOT / "results" / "judgments.jsonl").read_text(encoding="utf-8").splitlines())
             if p["config"] == best}

    # Explorer: two planted calls per defect, real calls the logs flag, and a few clean real calls.
    rng = random.Random(3)
    inj = [r for r in rows.values() if r["subset"] == "injected"]
    picks = []
    for d in sorted({r["meta"]["injected"] for r in inj}):
        picks += [r for r in inj if r["meta"]["injected"] == d][:2]
    real = [r for r in rows.values() if r["subset"] == "real"]
    flagged = [r for r in real if any(r["labels"].values())]
    clean = [r for r in real if not any(r["labels"].values())]
    picks = rng.sample(flagged, 10) + picks + rng.sample(clean, 4)
    explorer = [{"id": r["id"], "subset": r["subset"], "lang": r["meta"]["language"], "voice_config": r["meta"]["config"],
                 "injected": r["meta"].get("injected"), "turns": [{"speaker": t["speaker"], "text": t["text"]} for t in r["turns"]],
                 "labels": r["labels"], "judge": preds[r["id"]]["verdicts"]} for r in picks if r["id"] in preds]
    out = {"repo": args.repo, "author": args.author, "judge": best,
           "checks": [{"id": c.id, "name": c.name, "definition": c.definition} for c in CHECKS],
           "counts": {"real": sum(r["subset"] == "real" for r in rows.values()), "injected": len(inj)},
           "eval": ev, "insights": json.loads((ROOT / "results" / "insights.json").read_text()), "explorer": explorer}
    (ROOT / "docs" / "data.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("docs/data.json written;", len(explorer), "calls in the explorer; judge:", best)


if __name__ == "__main__":
    main()
