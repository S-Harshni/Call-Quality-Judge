"""Turn the best judge's verdicts on the real calls into a quality report (runs sql/insights.sql on an SQLite copy)."""
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def best_config(ev: dict) -> str:
    return max(ev["results"], key=lambda k: ev["results"][k]["all"]["macro_f1"] or 0)


def main() -> None:
    ev = json.loads((ROOT / "results" / "eval.json").read_text())
    best = best_config(ev)
    data = json.loads((ROOT / "data" / "eval_set.json").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in data["rows"] if r["subset"] == "real"}
    preds = [json.loads(l) for l in (ROOT / "results" / "judgments.jsonl").read_text(encoding="utf-8").splitlines()]
    preds = [p for p in preds if p["config"] == best and p["id"] in rows]
    db = ROOT / "out" / "insights.db"
    db.parent.mkdir(exist_ok=True)
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE calls (call_id TEXT, voice_config TEXT, language TEXT, behavior TEXT, expected TEXT);"
                      "CREATE TABLE verdicts (call_id TEXT, check_id TEXT, fail INTEGER, turn INTEGER, quote TEXT, evidence_ok INTEGER);"
                      "CREATE TABLE labels (call_id TEXT, check_id TEXT, fail INTEGER);")
    for p in preds:
        m = rows[p["id"]]["meta"]
        con.execute("INSERT INTO calls VALUES (?,?,?,?,?)", (p["id"], m["config"], m["language"], m["behavior"], m["expected"]))
        for c, v in p["verdicts"].items():
            if c == "tone":
                continue
            con.execute("INSERT INTO verdicts VALUES (?,?,?,?,?,?)", (p["id"], c, int(v["fail"]), v["turn"], v["quote"], int(v["evidence_ok"])))
            con.execute("INSERT INTO labels VALUES (?,?,?)", (p["id"], c, int(rows[p["id"]]["labels"][c])))
    con.commit()
    out = {"judge": best, "calls": len(preds)}
    for block in re.split(r"^-- name: ", (ROOT / "sql" / "insights.sql").read_text(), flags=re.M)[1:]:
        name, sql = block.split("\n", 1)
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        out[name.strip()] = [dict(zip(cols, r)) for r in cur.fetchall()]
    (ROOT / "results" / "insights.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["fail_rate_by_check"], indent=1))
    print(json.dumps(out["fail_rate_by_voice_config"], indent=1))


if __name__ == "__main__":
    main()
