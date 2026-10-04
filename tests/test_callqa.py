import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from callqa.judge import build_messages, judge, parse, quote_in  # noqa: E402
from callqa.labels import DEFECTS, inject, is_closing, repeated_question  # noqa: E402
from callqa.llm import ScriptedModel  # noqa: E402
from callqa.metrics import kappa, scores  # noqa: E402
from callqa.rubric import CHECK_IDS  # noqa: E402
from callqa.transcript import from_file, from_text  # noqa: E402

EX = ROOT / "examples"


def clean_call():
    c = from_file(EX / "english_good_call.txt")
    c.meta = {"language": "en", "expected": "booked"}
    return c


def test_parse_text_transcript():
    c = from_text("Agent: Hi there\nCustomer: hello\ncontinued line\nA: bye")
    assert [t.speaker for t in c.turns] == ["Agent", "Customer", "Agent"]
    assert c.turns[1].text == "hello continued line"
    assert c.render().startswith("[0] Agent: Hi there")


def test_quote_verification_rejects_invented_evidence():
    c = from_file(EX / "english_rate_promise.txt")
    assert quote_in(c, "you will get 8.5% for sure", 5)
    assert quote_in(c, "YOU WILL GET 8.5%, for sure!", None)  # case and punctuation are ignored
    assert not quote_in(c, "we charge 7% interest", 5)
    assert not quote_in(c, "What interest rate will I get", 4)  # the customer's words are not evidence against the agent


def test_parse_judge_json_and_flag_bad_quotes():
    c = from_file(EX / "english_rate_promise.txt")
    ans = {k: {"verdict": "pass", "turn": None, "quote": ""} for k in CHECK_IDS}
    ans["compliance"] = {"verdict": "FAIL", "turn": 5, "quote": "your approval is guaranteed"}
    ans["tone"] = {"verdict": "fail", "turn": 3, "quote": "something never said"}
    verdicts, ok = parse(c, "Here you go: " + json.dumps(ans))
    assert ok and verdicts["compliance"].fail and verdicts["compliance"].evidence_ok
    assert verdicts["tone"].fail and not verdicts["tone"].evidence_ok
    assert not verdicts["language"].fail


def test_broken_json_defaults_to_pass_and_is_counted():
    verdicts, ok = parse(clean_call(), "not json at all")
    assert not ok and not any(v.fail for v in verdicts.values())


def test_judge_with_scripted_model():
    ans = {k: {"verdict": "pass", "turn": None, "quote": ""} for k in CHECK_IDS}
    card = judge(ScriptedModel([json.dumps(ans)]), clean_call(), "rubric")
    assert card.score == 6 and card.json_ok


def test_few_shot_prompt_contains_examples():
    ex = [(clean_call(), {"compliance": {"verdict": "pass"}})]
    msgs = build_messages(clean_call(), "few_shot", ex)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert "Correct outcome" in msgs[0]["content"]
    assert len(build_messages(clean_call(), "zero_shot")) == 2


def test_label_helpers():
    assert is_closing("Thank you, Rahul, your advisor call is booked for Saturday 11 am.")
    assert not is_closing("Roughly how much loan do you need?")
    rep, turn, q = repeated_question(from_file(EX / "hinglish_repeat_question.txt"))
    assert rep and turn == 11 and "monthly income" in q


def test_every_defect_injects_exactly_its_label():
    rng = random.Random(0)
    for d in DEFECTS:
        c, labels, ev = inject(clean_call(), d, rng)
        target = "compliance" if d.startswith("compliance") else d
        assert labels[target], d
        assert quote_in(c, ev["quote"], ev["turn"]), d
        assert c.render() != clean_call().render()


def test_metrics():
    s = scores([True, True, False, False], [True, False, True, False])
    assert s["tp"] == 1 and s["precision"] == 0.5 and s["recall"] == 0.5 and s["accuracy"] == 0.5
    assert kappa([True, False], [True, False]) == 1.0
    assert scores([False, False], [False, False])["f1"] is None
