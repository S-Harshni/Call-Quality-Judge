"""Transcripts: load them from the voice agent's call database or from a plain text file, and render them for the judge."""
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Turn:
    speaker: str  # "Agent" or "Customer"
    text: str
    lang: str = ""


@dataclass
class Call:
    call_id: str
    turns: list[Turn]
    meta: dict = field(default_factory=dict)

    def agent_turns(self) -> list[tuple[int, Turn]]:
        return [(i, t) for i, t in enumerate(self.turns) if t.speaker == "Agent"]

    def render(self) -> str:
        """Numbered lines, so the judge can point at the turn it quotes."""
        return "\n".join(f"[{i}] {t.speaker}: {t.text}" for i, t in enumerate(self.turns))


def from_text(text: str, call_id: str = "call") -> Call:
    """Parse lines like 'Agent: ...' / 'Customer: ...' (also 'A:' / 'C:'). Lines without a speaker continue the previous turn."""
    turns: list[Turn] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(agent|customer|a|c|bot|user)\s*[:\-]\s*(.*)$", line, re.I)
        if m:
            who = "Agent" if m.group(1).lower() in ("agent", "a", "bot") else "Customer"
            turns.append(Turn(who, m.group(2).strip()))
        elif turns:
            turns[-1].text += " " + line
    if not turns:
        raise ValueError("no 'Agent:' or 'Customer:' lines found")
    return Call(call_id, turns)


def from_file(path: Path) -> Call:
    return from_text(Path(path).read_text(encoding="utf-8"), Path(path).stem)


def load_db(db: Path) -> list[Call]:
    """Every call in the voice agent's SQLite database, with its metadata (config, language, expected outcome...)."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    calls = []
    for c in con.execute("SELECT * FROM calls ORDER BY call_id"):
        turns = []
        for t in con.execute("SELECT * FROM turns WHERE call_id = ? ORDER BY idx", (c["call_id"],)):
            if t["customer"]:
                turns.append(Turn("Customer", t["customer"], t["customer_lang"] or ""))
            turns.append(Turn("Agent", t["reply"] or "", t["reply_lang"] or ""))
        meta = dict(c)
        meta["violations"] = [dict(v) for v in con.execute("SELECT kind, idx FROM violations WHERE call_id = ?", (c["call_id"],))]
        calls.append(Call(str(c["call_id"]), turns, meta))
    con.close()
    return calls
