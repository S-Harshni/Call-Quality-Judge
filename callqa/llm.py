"""Small client for local open-source models served by Ollama, with an on-disk cache.

Every request and response is cached by a hash of (model, messages, options), so an evaluation can be re-run and
re-scored exactly, and the measured latency of the original call is kept with the cached answer.
"""
import hashlib
import json
import threading
import time
from pathlib import Path

import httpx

OLLAMA = "http://localhost:11434/api/chat"


class ChatModel:
    def __init__(self, model: str, cache: Path | None = None, url: str = OLLAMA, timeout: float = 180):
        self.model, self.url, self.timeout = model, url, timeout
        self.cache_path = cache
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        if cache and cache.exists():
            for line in cache.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self._cache[row["key"]] = row

    def chat(self, messages: list[dict], json_mode: bool = False, temperature: float = 0.3, seed: int = 0,
             max_tokens: int = 220, num_ctx: int = 4096) -> tuple[str, float]:
        """Return (text, latency in ms). Cached answers return the latency measured when they were generated."""
        options = {"temperature": temperature, "seed": seed, "num_predict": max_tokens, "num_ctx": num_ctx}
        key = hashlib.sha256(json.dumps([self.model, messages, options, json_mode], ensure_ascii=False).encode()).hexdigest()
        if key in self._cache:
            row = self._cache[key]
            return row["text"], row["ms"]
        body = {"model": self.model, "messages": messages, "stream": False, "options": options, "keep_alive": "10m"}
        if json_mode:
            body["format"] = "json"
        for attempt in range(3):  # Ollama occasionally returns 500 under memory pressure; retry with a pause
            start = time.perf_counter()
            r = httpx.post(self.url, json=body, timeout=self.timeout)
            if r.status_code < 500:
                break
            if attempt == 1 and "format" in body:  # JSON-constrained decoding can fail on some Devanagari output;
                body = {k: v for k, v in body.items() if k != "format"}  # fall back to free text (the caller parses JSON)
            time.sleep(2)
        r.raise_for_status()
        ms = (time.perf_counter() - start) * 1000
        text = r.json()["message"]["content"]
        row = {"key": key, "model": self.model, "text": text, "ms": round(ms, 1)}
        with self._lock:
            self._cache[key] = row
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self.cache_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return text, ms


class ScriptedModel:
    """Stand-in model for tests and CI: returns queued answers in order."""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.model = "scripted"
        self.calls: list[list[dict]] = []

    def chat(self, messages, json_mode=False, temperature=0.3, seed=0, max_tokens=220, num_ctx=4096):
        self.calls.append(messages)
        return self.answers.pop(0), 1.0
