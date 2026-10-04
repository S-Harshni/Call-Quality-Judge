"""Write the results tables into README.md (between the <!-- results --> markers)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"zero_shot": "All six checks in one prompt, zero-shot", "rubric": "All six in one prompt, full rubric",
         "few_shot": "All six in one prompt, rubric + 2 examples", "per_check": "One focused prompt per check",
         "hybrid": "**Hybrid**: rules + focused LLM prompts + evidence gate"}
CHECKS = ["compliance", "language", "repeat_question", "next_step", "outcome", "tone"]
pct = lambda v: "–" if v is None else f"{v * 100:.0f}%"  # noqa: E731


def main() -> None:
    ev = json.loads((ROOT / "results" / "eval.json").read_text())["results"]
    ins = json.loads((ROOT / "results" / "insights.json").read_text())
    rows = ["| Judge design | Macro F1, planted defects (126 calls) | Macro F1, real calls (154) | LLM evidence verified | Valid JSON | Seconds per call |",
            "|---|---:|---:|---:|---:|---:|"]
    for k, v in ev.items():
        rows.append(f"| {NAMES[k.split(':')[0]]} | {pct(v['injected']['macro_f1'])} | {pct(v['real']['macro_f1'])} | {pct(v['evidence_valid'])} | "
                    f"{pct(v['json_ok'])} | {v['latency_p50_ms'] / 1000:.1f} |")
    per = ["| Check | " + " | ".join(NAMES[k.split(':')[0]].replace("**", "").split(":")[0] for k in ev) + " |",
           "|---|" + "---:|" * len(ev)]
    for c in CHECKS:
        per.append(f"| {c} | " + " | ".join(pct(v["injected"]["checks"][c]["f1"]) for v in ev.values()) + " |")
    hyb = next(v for k, v in ev.items() if k.startswith("hybrid"))
    real = ["| Check (real calls) | Recall | Precision | F1 |", "|---|---:|---:|---:|"]
    for c, m in hyb["real"]["checks"].items():
        real.append(f"| {c} | {pct(m['recall'])} | {pct(m['precision'])} | {pct(m['f1'])} |")
    found = ["| Check | Judge flags | Agent logs flag |", "|---|---:|---:|"]
    for r in ins["fail_rate_by_check"]:
        found.append(f"| {r['check_id']} | {pct(r['judge_fail_rate'])} | {pct(r['logged_fail_rate'])} |")
    cfg = ["| Voice agent version | Calls with no failed check |", "|---|---:|"]
    for r in ins["fail_rate_by_voice_config"]:
        cfg.append(f"| {r['voice_config']} | {pct(r['clean_call_share'])} |")
    text = "\n".join(["### Five judge designs\n", *rows, "\n### F1 per check on planted defects\n", *per,
                      "\n### Hybrid judge on real calls\n", *real, f"\n### What the judge found in {ins['calls']} real calls\n", *found, "", *cfg])
    readme = (ROOT / "README.md").read_text()
    readme = re.sub(r"<!-- results -->.*<!-- /results -->", "<!-- results -->\n" + text + "\n<!-- /results -->", readme, flags=re.S)
    (ROOT / "README.md").write_text(readme)
    print("README tables updated")


if __name__ == "__main__":
    main()
