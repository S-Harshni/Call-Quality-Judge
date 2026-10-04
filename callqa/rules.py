"""Rule-based checks for the three mechanical criteria, where code is exact, instant and free.

These rules are written for any transcript (no knowledge of the voice agent's scripted lines):
  language         each sentence is tagged English / Hinglish / Hindi (script + a romanised-Hindi word list); an agent
                   sentence in the other script from the customer's language fails (English inside Hinglish is normal)
  repeat_question  two agent questions in different turns sharing at least 80% of the shorter one's words
  next_step        the last agent turn is a question, or too short to state what happens next
"""
import re

from .transcript import Call

HINGLISH = set("""hai hain ho hoon hun tha thi the aap aapka aapki aapke apna apni mera meri mere main mai hum hamara hamare kya kaise kab kahan
kitna kitni kitne kaun kaunsa kyun nahi nahin na haan ji theek thik accha acha bahut sab kuch koi ke ki ka ko se mein me par pe aur ya bhi
toh to liye wala wali karna karte karta karti kar kariye kijiye dijiye batayein bataiye boliye chahiye raha rahi rahe gaya gayi hoga hogi
abhi kal aaj din samay baje shaam subah dobara batane lagbhag mahine maheene salary naukri ghar shukriya dhanyavaad""".split())
SENT = re.compile(r"[^.?!।]+[.?!।]?")


def sentence_lang(s: str) -> str | None:
    """'hi', 'hinglish', 'en', or None when the sentence is too short to tell."""
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return None
    if sum("ऀ" <= c <= "ॿ" for c in letters) / len(letters) > 0.3:
        return "hi"
    words = re.findall(r"[a-z]+", s.lower())
    if len(words) < 4:
        return None
    return "hinglish" if sum(w in HINGLISH for w in words) / len(words) >= 0.2 else "en"


def customer_lang(call: Call) -> str | None:
    votes = [sentence_lang(s) for t in call.turns if t.speaker == "Customer" for s in SENT.findall(t.text)]
    votes = [v for v in votes if v]
    return max(set(votes), key=votes.count) if votes else None


def check_language(call: Call):
    want = customer_lang(call)
    if not want:
        return False, None, ""
    for i, t in call.agent_turns():
        for s in SENT.findall(t.text):
            got = sentence_lang(s)
            # English and Hinglish mix naturally (both Latin script); a switch of script is what the customer cannot follow.
            if got and got != want and {got, want} != {"en", "hinglish"}:
                return True, i, s.strip()
    return False, None, ""


def _words(s: str) -> set[str]:
    return set(re.findall(r"\w+", s.lower()))


def check_repeat(call: Call):
    asked: list[tuple[int, str]] = []
    for i, t in call.agent_turns():
        for q in [s.strip() for s in SENT.findall(t.text) if s.strip().endswith("?")]:
            for j, prev in asked:
                a, b = _words(q), _words(prev)
                if j != i and min(len(a), len(b)) >= 3 and len(a & b) / min(len(a), len(b)) >= 0.8:
                    return True, i, q
            asked.append((i, q))
    return False, None, ""


def check_next_step(call: Call):
    agent = call.agent_turns()
    if not agent:
        return True, None, ""
    i, last = agent[-1]
    text = last.text.strip()
    if text.endswith("?") or len(re.findall(r"\w+", text)) < 5:
        return True, i, text
    return False, None, ""


RULES = {"language": check_language, "repeat_question": check_repeat, "next_step": check_next_step}
