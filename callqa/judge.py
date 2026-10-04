"""The judge: one LLM call scores all six checks and must quote the turn behind every FAIL.

Three prompt variants are compared in the evaluation:
  zero_shot  one-line question per check
  rubric     full pass / fail definitions and the business rules
  few_shot   the rubric plus two worked examples
The quote is verified against the transcript in code, so a verdict with invented evidence is caught.
"""
import json
import re
from dataclasses import dataclass, field

from .rubric import CHECK_IDS, CHECKS, CONTEXT
from .transcript import Call

VARIANTS = ["zero_shot", "rubric", "few_shot", "per_check", "hybrid"]
FORMAT = ('Answer with JSON only, one key per check: {"compliance": {"verdict": "pass" or "fail", "turn": <turn number or null>, '
          '"quote": "<exact words from that turn, only for a fail>"}, ... for ' + ", ".join(CHECK_IDS) + "}.")


@dataclass
class Verdict:
    check: str
    fail: bool
    turn: int | None = None
    quote: str = ""
    evidence_ok: bool = True   # for a FAIL: the quote really appears in the transcript


@dataclass
class Scorecard:
    call_id: str
    verdicts: dict[str, Verdict]
    json_ok: bool
    ms: float
    raw: str = field(default="", repr=False)

    @property
    def failed(self) -> list[str]:
        return [c for c, v in self.verdicts.items() if v.fail]

    @property
    def score(self) -> int:
        """Checks passed out of six."""
        return len(CHECK_IDS) - len(self.failed)


def _system(variant: str) -> str:
    if variant == "zero_shot":
        checks = "\n".join(f"- {c.id}: {c.question}" for c in CHECKS)
        return f"You are a call-centre quality reviewer. Score the call transcript on these checks:\n{checks}\n{FORMAT}"
    checks = "\n".join(f"- {c.id} ({c.name}): {c.definition}" for c in CHECKS)
    return (f"You are a strict call-centre quality reviewer. {CONTEXT}\nScore the transcript on each check, reading every agent "
            f"turn. Judge only what is in the transcript.\n{checks}\nFor every fail give the turn number and copy the exact words "
            f"that break the rule. {FORMAT}")


def build_messages(call: Call, variant: str, examples: list[tuple[Call, dict]] | None = None) -> list[dict]:
    msgs = [{"role": "system", "content": _system(variant)}]
    if variant == "few_shot":
        for ex_call, ex_answer in examples or []:
            msgs += [{"role": "user", "content": f"Transcript:\n{ex_call.render()}"},
                     {"role": "assistant", "content": json.dumps(ex_answer, ensure_ascii=False)}]
    msgs.append({"role": "user", "content": f"Transcript:\n{call.render()}"})
    return msgs


_norm = lambda s: re.sub(r"[\s\W_]+", " ", s.lower()).strip()  # noqa: E731


def quote_in(call: Call, quote: str, turn: int | None) -> bool:
    """True if the quote (ignoring case and punctuation) is the agent's words: in the given agent turn, or in any agent turn.
    Quoting the customer is not evidence against the agent."""
    q = _norm(quote)
    if len(q) < 3:
        return False
    if turn is not None and 0 <= turn < len(call.turns) and call.turns[turn].speaker == "Agent" and q in _norm(call.turns[turn].text):
        return True
    return any(q in _norm(t.text) for _, t in call.agent_turns())


def parse(call: Call, text: str) -> tuple[dict[str, Verdict], bool]:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
        ok = isinstance(data, dict) and all(isinstance(data.get(c), dict) for c in CHECK_IDS)
    except json.JSONDecodeError:
        data, ok = {}, False
    verdicts = {}
    for c in CHECK_IDS:
        d = data.get(c) if isinstance(data.get(c), dict) else {}
        fail = str(d.get("verdict", "pass")).strip().lower().startswith("fail")
        turn = d.get("turn") if isinstance(d.get("turn"), int) else None
        quote = str(d.get("quote") or "")
        verdicts[c] = Verdict(c, fail, turn, quote, quote_in(call, quote, turn) if fail else True)
    return verdicts, ok


CHECK_FORMAT = ('Answer with JSON only: {"verdict": "pass" or "fail", "turn": <turn number or null>, '
                '"quote": "<exact words the agent said in that turn, only for a fail>"}.')


def check_messages(call: Call, check) -> list[dict]:
    """One focused question: a single check, its definition, and the transcript."""
    system = (f"You are a strict call-centre quality reviewer. {CONTEXT}\nCheck ONE thing only: {check.name}.\n{check.definition}\n"
              f"Read every agent turn carefully, one by one, before answering. {CHECK_FORMAT}")
    return [{"role": "system", "content": system}, {"role": "user", "content": f"Transcript:\n{call.render()}"}]


def judge_per_check(llm, call: Call, seed: int = 7, rules: bool = False) -> Scorecard:
    """One LLM question per check.

    With rules=True (the hybrid judge): code decides the three mechanical checks, the outcome check is LLM fact extraction plus
    code rules, and an LLM FAIL whose quote is not the agent's words is dropped (evidence gate)."""
    from .outcome import check_outcome
    from .rules import RULES
    verdicts, ok_all, total = {}, True, 0.0
    for check in CHECKS:
        if rules and check.id in RULES:
            fail, turn, quote = RULES[check.id](call)
            verdicts[check.id] = Verdict(check.id, fail, turn, quote, True)
            continue
        if rules and check.id == "outcome":
            fail, turn, quote, ms, ok = check_outcome(llm, call, seed)
            total += ms
            ok_all &= ok
            verdicts[check.id] = Verdict(check.id, fail, turn, quote, True)
            continue
        text, ms = llm.chat(check_messages(call, check), json_mode=True, temperature=0.0, seed=seed, max_tokens=120, num_ctx=4096)
        total += ms
        m = re.search(r"\{.*\}", text, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
            ok = isinstance(d, dict) and "verdict" in d
        except json.JSONDecodeError:
            d, ok = {}, False
        ok_all &= ok
        fail = str(d.get("verdict", "pass")).strip().lower().startswith("fail")
        turn = d.get("turn") if isinstance(d.get("turn"), int) else None
        quote = str(d.get("quote") or "")
        evidence = quote_in(call, quote, turn) if fail else True
        if rules and fail and not evidence:  # evidence gate: an unverifiable FAIL is not reported
            fail, turn, quote, evidence = False, None, "", True
        verdicts[check.id] = Verdict(check.id, fail, turn, quote, evidence)
    return Scorecard(call.call_id, verdicts, ok_all, total)


def judge(llm, call: Call, variant: str = "few_shot", examples: list[tuple[Call, dict]] | None = None, seed: int = 7) -> Scorecard:
    if variant in ("per_check", "hybrid"):
        return judge_per_check(llm, call, seed, rules=variant == "hybrid")
    text, ms = llm.chat(build_messages(call, variant, examples), json_mode=True, temperature=0.0, seed=seed, max_tokens=400,
                        num_ctx=8192)  # few-shot prompts hold three transcripts
    verdicts, ok = parse(call, text)
    return Scorecard(call.call_id, verdicts, ok, ms, text)
