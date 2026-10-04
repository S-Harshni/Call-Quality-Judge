# Call Quality Judge

![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python&logoColor=white)
![LLM](https://img.shields.io/badge/LLM-Qwen%202.5%203B%20(Ollama)-555)
![Tests](https://github.com/S-Harshni/Call-Quality-Judge/actions/workflows/tests.yml/badge.svg)

**Live page:** [s-harshni.github.io/Call-Quality-Judge](https://s-harshni.github.io/Call-Quality-Judge/) · 👤 **Portfolio:** [s-harshni.github.io/S-Harshni](https://s-harshni.github.io/S-Harshni/)

An LLM judge that reviews **Hindi, Hinglish and English sales calls** the way a call-centre QA reviewer does: six pass/fail
checks, and the **exact words behind every failure**. It runs on a laptop with an open-source 3B model, and it is
**measured**: five judge designs are compared on 282 labelled calls.

```text
$ python -m callqa score examples/english_rate_promise.txt examples/hinglish_repeat_question.txt

english_rate_promise: 5/6 checks passed  (2.8s)
  FAIL  Compliance  turn 2: "Don't worry, you will get 8.5% for sure and your approval is guaranteed."
  PASS  Language match
  PASS  No repeated questions
  PASS  Clear next step
  PASS  Correct outcome
  PASS  Polite tone

hinglish_repeat_question: 5/6 checks passed  (2.7s)
  PASS  Compliance
  PASS  Language match
  FAIL  No repeated questions  turn 11: 'Aur aapki monthly income lagbhag kitni hai?'
  PASS  Clear next step
  PASS  Correct outcome
  PASS  Polite tone
```

## The six checks

| Check | Fails when | Decided by |
|---|---|---|
| Compliance | the agent promises a rate or an approval, or asks for an OTP / PIN / Aadhaar / PAN | LLM (focused prompt) |
| Language match | the agent switches script away from the customer's language (Devanagari ↔ Latin) | rules |
| No repeated questions | the agent asks the same question in two turns | rules |
| Clear next step | the call ends on a question, or without saying what happens next | rules |
| Correct outcome | the ending contradicts the lending rules or what the customer said | LLM reads the facts, code applies the rules |
| Polite tone | any agent turn is rude, impatient or pressuring | LLM (focused prompt) |

## How the judge works

```text
transcript ──► rules (callqa/rules.py) ─────────────► language, repeated questions, next step
           ├─► one focused LLM prompt per check ────► compliance, tone      ──► evidence gate: the quote must be the
           └─► LLM extracts facts + the ending ──► code applies the lending rules ──► outcome      agent's own words
```

- **Rules where code is exact.** Script detection plus a romanised-Hindi word list tags each sentence's language;
  word overlap finds repeated questions; the last turn shows whether a next step was stated. Instant, free, explainable.
- **One question at a time for the LLM.** A 3B model asked to score all six checks in one prompt mostly answers "pass".
  Six short prompts work far better.
- **LLM reads, code decides.** For the outcome the model only copies what the customer said (loan amount, income,
  "call me later", "wrong number") and classifies the agent's last line. Amounts are parsed in code (lakh / crore /
  thousand, Hindi number words, Devanagari digits) and the lending rules pick the right ending.
- **Evidence gate.** Every LLM failure must quote the agent. The quote is checked against the transcript; a quote of
  the customer, or one that was never said, is dropped instead of reported.

## How it is measured

| Set | Calls | Labels |
|---|---:|---|
| Planted defects | 126 | 7 defect types (rate promise, OTP request, script switch, repeated question, abrupt ending, wrong outcome, rude line) × 6 clean calls per language, one defect written into each: the label is exact |
| Real calls | 154 | every call of the [Voice Sales Agent](https://github.com/S-Harshni/Voice-Sales-Agent) evaluation: compliance from the agent's detector logs, outcome from each simulated customer's true profile |

Real calls are scored only on compliance and outcome. The agent's logs recognise only its own scripted wording for the
other checks, so they miss problems the judge can see (for example "Is that convenient for you?" asked twice); those
disagreements are reported as findings, not counted as judge errors. Two calls are held out as few-shot examples.

<!-- results -->
### Five judge designs

| Judge design | Macro F1, planted defects (126 calls) | Macro F1, real calls (154) | LLM evidence verified | Valid JSON | Seconds per call |
|---|---:|---:|---:|---:|---:|
| All six checks in one prompt, zero-shot | 8% | 18% | 76% | 96% | 4.5 |
| All six in one prompt, full rubric | 17% | 44% | 75% | 98% | 4.0 |
| All six in one prompt, rubric + 2 examples | 18% | 32% | 79% | 100% | 4.3 |
| One focused prompt per check | 45% | 27% | 84% | 95% | 6.1 |
| **Hybrid**: rules + focused LLM prompts + evidence gate | 86% | 21% | 100% | 100% | 4.3 |

### F1 per check on planted defects

| Check | All six checks in one prompt, zero-shot | All six in one prompt, full rubric | All six in one prompt, rubric + 2 examples | One focused prompt per check | Hybrid |
|---|---:|---:|---:|---:|---:|
| compliance | 33% | 67% | 68% | 76% | 76% |
| language | 0% | 0% | 10% | 49% | 100% |
| repeat_question | 0% | 0% | 0% | 21% | 100% |
| next_step | 9% | 20% | 13% | 24% | 100% |
| outcome | 9% | 16% | 17% | 48% | 91% |
| tone | 0% | 0% | 0% | 50% | 50% |

### Hybrid judge on real calls

| Check (real calls) | Recall | Precision | F1 |
|---|---:|---:|---:|
| compliance | 0% | 0% | 0% |
| outcome | 41% | 44% | 42% |

### What the judge found in 154 real calls

| Check | Judge flags | Agent logs flag |
|---|---:|---:|
| repeat_question | 41% | 27% |
| outcome | 22% | 24% |
| compliance | 9% | 3% |
| next_step | 7% | 15% |
| language | 3% | 2% |

| Voice agent version | Calls with no failed check |
|---|---:|
| persona:llama3.2:3b:code_flow | 69% |
| persona:qwen2.5:3b:code_flow | 65% |
| few_shot:qwen2.5:3b:code_flow | 62% |
| persona:gemma2:2b:code_flow | 42% |
| zero_shot:qwen2.5:3b:code_flow | 31% |
| persona:qwen2.5:3b:llm_flow | 8% |
<!-- /results -->

## What I changed along the way

1. **All six checks in one prompt** (zero-shot, rubric, few-shot): a 3B model said "pass" to almost everything.
2. **One focused prompt per check:** much better recall, but it over-flagged language and repeated questions,
   which code can check exactly.
3. **Hybrid:** rules for the three mechanical checks. Reviewing the outcome errors showed the model doing eligibility
   arithmetic in its head and ticking "wants a callback" for customers who had just booked, so the outcome check became
   fact extraction with quotes that must be the customer's words, plus code rules.
4. **Evidence gate:** reviewing compliance false alarms showed most quoted the customer or words never said.
5. **Bugs found in my own test set:** some planted "repeats" repeated a question that was never asked, and some defects
   landed in the closing line. Both were fixed and the planted set was rebuilt.

**Known limits.**
- Tone is the weakest check: the 3B model misses many rude lines (the Hindi example in `examples/` is one).
- On real calls the judge caught **none of the 4 compliance violations** the agent's logs recorded: they sit in garbled
  replies, and the judge quoted the customer instead of the agent, so the evidence gate dropped them. Four cases are too
  few to tune on; this is the clearest next step.
- The turn number the model gives is sometimes off; the quote is what is verified and highlighted.
- Rule results on planted defects are high partly because the same author wrote the rules and the defects; the real
  calls are the harder test.

## Run it

```bash
ollama pull qwen2.5:3b
pip install -r requirements.txt
python -m callqa score examples/*.txt                  # scorecards (hybrid judge)
python -m callqa score my_call.txt --json              # machine-readable
python -m callqa batch data/calls.db --out out/judged.db   # every call into SQLite
```

Transcripts are plain text, one turn per line: `Agent: ...` / `Customer: ...`.

Reproduce the evaluation:

```bash
python eval/build_dataset.py && python eval/run_eval.py && python eval/insights.py && python eval/report.py
pytest -q
```

## Project structure

```
callqa/
  rubric.py       the six checks and their pass / fail definitions
  judge.py        prompt designs, JSON parsing, evidence verification, the hybrid judge
  rules.py        language, repeated-question and next-step rules
  outcome.py      fact extraction + lending rules for the outcome check
  numbers.py      Indian amount parser (lakh, crore, Hindi number words)
  labels.py       reference labels from the agent's logs and defect injection
  transcript.py   load calls from text files or the voice agent's SQLite database
  llm.py          Ollama client with an on-disk cache
eval/             dataset, evaluation, SQL insights, README tables, page data
sql/insights.sql  quality report queries
docs/             project page (GitHub Pages)
examples/         four transcripts to try
```

## License

MIT
