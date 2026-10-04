"""Command line.

  python -m callqa score examples/hinglish_repeat_question.txt   score one transcript (hybrid judge) and print a scorecard
  python -m callqa score call.txt --json                    the same, as JSON
  python -m callqa batch data/calls.db --out out/judged.db  score every call in a voice-agent database into SQLite
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .judge import VARIANTS, judge
from .llm import ChatModel
from .rubric import BY_ID, CHECK_IDS
from .transcript import from_file, load_db

ROOT = Path(__file__).resolve().parents[1]
GREEN, RED, DIM, BOLD, END = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def examples():
    """The two worked examples used by the few-shot prompt."""
    from .transcript import Call, Turn
    data = json.loads((ROOT / "data" / "eval_set.json").read_text(encoding="utf-8"))
    return [(Call(e["id"], [Turn(t["speaker"], t["text"]) for t in e["turns"]]), e["answer"]) for e in data["examples"]]


def print_card(call, card, color=True):
    c = (lambda code, s: f"{code}{s}{END}") if color and sys.stdout.isatty() else (lambda code, s: s)
    print(c(BOLD, f"\n{call.call_id}: {card.score}/6 checks passed") + c(DIM, f"  ({card.ms / 1000:.1f}s)"))
    for cid in CHECK_IDS:
        v = card.verdicts[cid]
        if not v.fail:
            print(f"  {c(GREEN, 'PASS')}  {BY_ID[cid].name}")
            continue
        where = f"turn {v.turn}: " if v.turn is not None else ""
        note = "" if v.evidence_ok else c(DIM, "  (quote not found in transcript)")
        print(f"  {c(RED, 'FAIL')}  {BY_ID[cid].name}  {c(DIM, where + repr(v.quote))}{note}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="callqa", description="Score sales-call transcripts with an LLM judge.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score", help="score transcript files ('Agent: ...' / 'Customer: ...' lines)")
    s.add_argument("files", nargs="+", type=Path)
    s.add_argument("--json", action="store_true")
    b = sub.add_parser("batch", help="score every call in a voice-agent SQLite database")
    b.add_argument("db", type=Path)
    b.add_argument("--out", type=Path, default=ROOT / "out" / "judged.db")
    for p in (s, b):
        p.add_argument("--model", default="qwen2.5:3b")
        p.add_argument("--variant", default="hybrid", choices=VARIANTS)
    args = ap.parse_args(argv)
    llm = ChatModel(args.model, cache=ROOT / "out" / "llm_cache.jsonl")
    ex = examples() if args.variant == "few_shot" else None

    if args.cmd == "score":
        for f in args.files:
            call = from_file(f)
            card = judge(llm, call, args.variant, ex)
            if args.json:
                print(json.dumps({"call": call.call_id, "score": card.score, "checks": {k: vars(v) for k, v in card.verdicts.items()}},
                                 ensure_ascii=False, indent=1))
            else:
                print_card(call, card)
        return

    calls = load_db(args.db)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(args.out)
    con.execute("CREATE TABLE IF NOT EXISTS verdicts (call_id TEXT, check_id TEXT, fail INTEGER, turn INTEGER, quote TEXT, evidence_ok INTEGER)")
    con.execute("DELETE FROM verdicts")
    for n, call in enumerate(calls, 1):
        card = judge(llm, call, args.variant, ex)
        con.executemany("INSERT INTO verdicts VALUES (?,?,?,?,?,?)",
                        [(call.call_id, v.check, int(v.fail), v.turn, v.quote, int(v.evidence_ok)) for v in card.verdicts.values()])
        print(f"\r{n}/{len(calls)} calls scored", end="", flush=True)
    con.commit()
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
