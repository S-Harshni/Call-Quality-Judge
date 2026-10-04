"""Correct-outcome check: the LLM reads the facts, code applies the lending rules.

A 3B model asked "was the outcome right?" has to do eligibility arithmetic in its head and mostly guesses. Here it only
extracts what the customer said (copying the words for the amounts) and how the call ended; numbers are parsed by
callqa/numbers.py (lakh / crore / thousand, Hindi number words) and the rules below decide the expected ending.
"""
import json
import re

from .numbers import SCALE, amounts
from .transcript import Call

ENDINGS = ["booked", "callback", "not_eligible", "not_interested", "wrong_number", "none"]
MIN_INCOME_K, LOAN_LAKH = 25, (5, 500)
PROMPT = ("You read a sales-call transcript between Priya (agent, Ghar Home Loans) and a customer. Copy the CUSTOMER's exact "
          "words as evidence; leave a field empty when the customer did not say it. Answer with JSON only:\n"
          '{"wrong_person_quote": "customer words saying they are not the right person or never asked about a loan",\n'
          ' "not_interested_quote": "customer words saying they do not want a loan or not to call again",\n'
          ' "callback_quote": "customer words saying they are busy and asking to be called later",\n'
          ' "loan_said": "customer words giving the loan amount",\n'
          ' "income_said": "customer words giving their MONTHLY income"}')
ENDING_PROMPT = ("This is the last thing a home-loan sales agent said before the call ended. Classify it. Answer with JSON only: "
                 '{"ending": "booked" if it confirms an advisor call booked for a day or time, "callback" if it promises to call '
                 'back later, "not_eligible" if it says a loan cannot be offered now, "not_interested" if it accepts the customer '
                 'does not want it, "wrong_number" if it apologises for calling the wrong person, or "none" if it says none of '
                 'these (for example just "okay", a question, or small talk)}')


def _value(said: str, per_unit: int, lo: float, hi: float) -> float | None:
    vals = [v * SCALE[u] / per_unit for v, u in amounts(said or "")]
    fits = [v for v in vals if lo <= v <= hi]
    return fits[0] if fits else None


def _said(call: Call, quote) -> bool:
    """The quote is really in a customer turn (case and punctuation ignored)."""
    from .judge import _norm
    q = _norm(str(quote or ""))
    return len(q) >= 3 and any(q in _norm(t.text) for t in call.turns if t.speaker == "Customer")


def read_facts(call: Call, raw: dict) -> dict:
    """Keep an intent only when its evidence is the customer's own words."""
    return {"wrong_person": _said(call, raw.get("wrong_person_quote")), "not_interested": _said(call, raw.get("not_interested_quote")),
            "wants_callback": _said(call, raw.get("callback_quote")), "loan_said": str(raw.get("loan_said") or ""),
            "income_said": str(raw.get("income_said") or "")}


def expected_ending(facts: dict) -> str | None:
    """The ending the lending rules require, or None when the transcript does not hold enough facts to say."""
    income = _value(facts.get("income_said", ""), 1_000, 3, 2_000)
    loan = _value(facts.get("loan_said", ""), 100_000, 0.5, 5_000)
    if (income is not None and income < MIN_INCOME_K) or (loan is not None and not LOAN_LAKH[0] <= loan <= LOAN_LAKH[1]):
        return "not_eligible"  # facts the customer gave outrank the model's reading of their intent
    if facts.get("wrong_person") and income is None and loan is None:
        return "wrong_number"
    if facts.get("not_interested"):
        return "not_interested"
    if income is None and loan is None:
        # A busy customer asks for a callback before giving any amounts; once they have answered the qualifying
        # questions, a day and time they give is the advisor slot, not a callback request.
        return "callback" if facts.get("wants_callback") else None
    return "booked"


def _json(text: str) -> tuple[dict, bool]:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
        return (d, True) if isinstance(d, dict) else ({}, False)
    except json.JSONDecodeError:
        return {}, False


def check_outcome(llm, call: Call, seed: int = 7):
    """(fail, turn, quote, ms, json_ok): facts from the whole call, the ending from the agent's last turn alone."""
    agent = call.agent_turns()
    if not agent:
        return True, None, "", 0.0, True
    last_i, last = agent[-1]
    text, ms1 = llm.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": f"Transcript:\n{call.render()}"}],
                         json_mode=True, temperature=0.0, seed=seed, max_tokens=160, num_ctx=4096)
    raw, ok1 = _json(text)
    facts = read_facts(call, raw)
    text, ms2 = llm.chat([{"role": "system", "content": ENDING_PROMPT}, {"role": "user", "content": last.text}],
                         json_mode=True, temperature=0.0, seed=seed, max_tokens=20)
    ending, ok2 = _json(text)
    got = str(ending.get("ending") or next((e for e in ENDINGS if e in text.lower()), "none")).strip().lower()
    want = expected_ending(facts)
    fail = want is not None and got != want
    return fail, (last_i if fail else None), (last.text if fail else ""), ms1 + ms2, ok1 and ok2
