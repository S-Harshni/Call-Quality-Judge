"""Run every judge configuration on the evaluation set and score it against the reference labels."""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from callqa.judge import judge  # noqa: E402
from callqa.llm import ChatModel  # noqa: E402
from callqa.metrics import scores  # noqa: E402
from callqa.rubric import CHECK_IDS  # noqa: E402
from callqa.transcript import Call, Turn  # noqa: E402

CONFIGS = [("zero_shot", "qwen2.5:3b"), ("rubric", "qwen2.5:3b"), ("few_shot", "qwen2.5:3b"), ("per_check", "qwen2.5:3b"),
           ("hybrid", "qwen2.5:3b")]
REAL_CHECKS = ["compliance", "outcome"]  # the checks whose labels on real calls are reliable (see README)


def to_call(row) -> Call:
    return Call(row["id"], [Turn(t["speaker"], t["text"], t["lang"]) for t in row["turns"]], row["meta"])


def summarize(rows, preds, variant: str = "") -> dict:
    out = {}
    for subset in ("real", "injected", "all"):
        idx = [i for i, r in enumerate(rows) if subset == "all" or r["subset"] == subset]
        per = {}
        for c in CHECK_IDS:
            if subset == "real" and c not in REAL_CHECKS:
                continue  # the logs only recognise the agent's scripted wording for these, so real calls are not scored on them
            if subset == "all" and c not in REAL_CHECKS:
                idx_c = [i for i in idx if rows[i]["subset"] == "injected"]
                per[c] = scores([preds[i]["verdicts"][c]["fail"] for i in idx_c], [rows[i]["labels"][c] for i in idx_c])
                continue
            per[c] = scores([preds[i]["verdicts"][c]["fail"] for i in idx], [rows[i]["labels"][c] for i in idx])
        f1s = [v["f1"] for v in per.values() if v["f1"] is not None]
        out[subset] = {"n": len(idx), "checks": per, "macro_f1": round(statistics.mean(f1s), 3) if f1s else None,
                       "accuracy": round(statistics.mean(v["accuracy"] for v in per.values()), 3)}
    from callqa.rules import RULES
    llm_checks = [c for c in CHECK_IDS if not (variant == "hybrid" and c in RULES)]  # rule verdicts quote the transcript by construction
    fails = [p["verdicts"][c] for p in preds for c in llm_checks if p["verdicts"][c]["fail"]]
    out["evidence_valid"] = round(sum(v["evidence_ok"] for v in fails) / len(fails), 3) if fails else None
    out["json_ok"] = round(sum(p["json_ok"] for p in preds) / len(preds), 3)
    out["latency_p50_ms"] = round(statistics.median(p["ms"] for p in preds))
    return out


def main() -> None:
    data = json.loads((ROOT / "data" / "eval_set.json").read_text(encoding="utf-8"))
    held = set(data["held_out_real_ids"])
    rows = [r for r in data["rows"] if r["id"] not in held]
    examples = [(to_call(e), e["answer"]) for e in data["examples"]]
    cache = ROOT / "out" / "llm_cache.jsonl"
    results, all_preds = {}, {}
    for variant, model in CONFIGS:
        name = f"{variant}:{model}"
        llm = ChatModel(model, cache=cache)
        preds = []
        for r in rows:
            s = judge(llm, to_call(r), variant, examples)
            preds.append({"id": r["id"], "json_ok": s.json_ok, "ms": s.ms,
                          "verdicts": {c: vars(v) for c, v in s.verdicts.items()}})
        results[name] = summarize(rows, preds, variant)
        all_preds[name] = preds
        print(name, json.dumps({k: results[name][k] for k in ("evidence_valid", "json_ok", "latency_p50_ms")}),
              "macro F1 real/injected:", results[name]["real"]["macro_f1"], results[name]["injected"]["macro_f1"], flush=True)
        (ROOT / "results").mkdir(exist_ok=True)  # saved after every configuration
        (ROOT / "results" / "eval.json").write_text(json.dumps({"n_rows": len(rows), "results": results}, indent=1))
        with (ROOT / "results" / "judgments.jsonl").open("w", encoding="utf-8") as f:
            for cfg, ps in all_preds.items():
                for p in ps:
                    f.write(json.dumps({"config": cfg, **p}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
