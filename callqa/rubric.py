"""The quality rubric: six checks a call-centre QA reviewer would score, with the business rules the judge needs."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    id: str
    name: str
    question: str      # one line, used by the zero-shot prompt
    definition: str    # full pass / fail rule, used by the rubric and few-shot prompts


CHECKS = [
    Check("compliance", "Compliance",
          "Did the agent promise a rate or an approval, or ask for sensitive data?",
          "FAIL if the agent quotes or promises an interest rate, promises or guarantees loan approval, or asks for an OTP, PIN, "
          "password, card number, Aadhaar or PAN number. Saying an advisor will share the rate is a PASS."),
    Check("language", "Language match",
          "Did the agent reply in the customer's language?",
          "The customer may speak English, Hindi (Devanagari) or Hinglish (Hindi in Latin letters). FAIL if any agent turn switches "
          "to a different language from the customer's (for example an English sentence to a Hindi speaker, or Devanagari to an "
          "English speaker). Brand names, numbers and words like 'loan' or 'thank you' inside Hinglish are fine."),
    Check("repeat_question", "No repeated questions",
          "Did the agent ask the same question twice?",
          "FAIL if the agent asks essentially the same question in two different turns (for example asking for monthly income "
          "twice). Customers hate repeating themselves, so flag it even if the first answer was unclear."),
    Check("next_step", "Clear next step",
          "Did the call end with a clear next step?",
          "PASS if the agent's last turn closes the call with a concrete next step: a booked advisor slot, an agreed callback time, "
          "a polite goodbye after the customer declined or was not eligible, or a record update for a wrong number. FAIL if the call "
          "just stops, ends on an unanswered question, or ends without saying what happens next."),
    Check("outcome", "Correct outcome",
          "Did the call reach the right outcome for this customer?",
          "Rules: book an advisor call only for an interested customer with monthly income of at least 25 thousand rupees and a "
          "loan between 5 lakh and 5 crore; otherwise tell them they are not eligible. If the customer is busy, agree a callback; "
          "if not interested, stop; if it is the wrong person, apologise and end. FAIL if the ending contradicts these rules or "
          "what the customer said (for example booking an ineligible customer, or rejecting an eligible one)."),
    Check("tone", "Polite tone",
          "Was the agent polite and respectful throughout?",
          "FAIL if any agent turn is rude, dismissive, impatient, sarcastic or pressures the customer (for example 'just answer the "
          "question' or 'I don't have all day'). Short, plain replies are fine."),
]
CHECK_IDS = [c.id for c in CHECKS]
BY_ID = {c.id: c for c in CHECKS}
CONTEXT = ("The transcript is an outbound call from Priya, a voice agent of Ghar Home Loans (a home-loan lender), to a lead who left "
           "their number on the website. Her goal is to qualify the lead and book a free 15-minute call with a loan advisor.")
